from __future__ import annotations
import asyncio, time, secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from game import GameError, GameRoom

BASE=Path(__file__).parent
ALPHABET='23456789ABCDEFGHJKLMNPQRSTUVWXYZ'
class NameBody(BaseModel): name:str=Field(min_length=1,max_length=24)
class Manager:
    def __init__(self): self.rooms={}; self.connections={}; self.locks={}
    def code(self):
        while True:
            c=''.join(secrets.choice(ALPHABET) for _ in range(6))
            if c not in self.rooms:return c
    def create(self,name):
        c=self.code(); r=GameRoom(c); p=r.add_player(name); self.rooms[c]=r; self.connections[c]={}; self.locks[c]=asyncio.Lock(); return r,p
    def get(self,c):
        r=self.rooms.get(c.upper())
        if not r: raise GameError('Spielraum nicht gefunden.')
        return r
manager=Manager()

def payload(r,p): return {'roomCode':r.code,'playerId':p.id,'token':p.token,'name':p.name}
async def broadcast(code):
    r=manager.rooms.get(code)
    if not r:return
    for pid,ws in list(manager.connections.get(code,{}).items()):
        try: await ws.send_json({'type':'state','state':r.public_state(pid)})
        except Exception: manager.connections[code].pop(pid,None)

@asynccontextmanager
async def lifespan(app):
    yield
app=FastAPI(title='Wer ist das? – Chemie',lifespan=lifespan)
@app.get('/')
async def index(): return FileResponse(BASE/'index.html')
@app.get('/app.js')
async def js(): return FileResponse(BASE/'app.js',media_type='text/javascript')
@app.get('/styles.css')
async def css(): return FileResponse(BASE/'styles.css',media_type='text/css')
@app.get('/manifest.webmanifest')
async def manifest(): return FileResponse(BASE/'manifest.webmanifest',media_type='application/manifest+json')
@app.get('/health')
async def health(): return {'status':'ok','rooms':len(manager.rooms)}
@app.post('/api/rooms')
async def create(body:NameBody):
    try:r,p=manager.create(body.name)
    except GameError as e: raise HTTPException(400,str(e))
    return payload(r,p)
@app.post('/api/rooms/{code}/join')
async def join(code:str,body:NameBody):
    try:r=manager.get(code); p=r.add_player(body.name)
    except GameError as e: raise HTTPException(400,str(e))
    return payload(r,p)

@app.websocket('/ws/{code}/{pid}')
async def ws_endpoint(ws:WebSocket,code:str,pid:str):
    await ws.accept(); code=code.upper(); token=ws.query_params.get('token','')
    try:r=manager.get(code); r.authenticate(pid,token)
    except GameError as e:
        await ws.send_json({'type':'error','message':str(e),'fatal':True}); await ws.close(code=4401); return
    manager.connections[code][pid]=ws; r.mark_connected(pid,True); await broadcast(code)
    try:
        while True:
            m=await ws.receive_json(); action=m.get('type'); lock=manager.locks[code]
            try:
                async with lock:
                    if action=='start':r.start(pid)
                    elif action=='eliminate':r.eliminate(pid,int(m.get('index')))
                    elif action=='end_turn':r.end_turn(pid)
                    elif action=='guess':r.guess(pid,int(m.get('index')))
                    elif action=='again':r.reset(pid)
                    elif action=='ping':pass
                    else:raise GameError('Unbekannte Aktion.')
            except (GameError,ValueError) as e: await ws.send_json({'type':'error','message':str(e),'fatal':False})
            await broadcast(code)
    except WebSocketDisconnect: pass
    except Exception: pass
    finally:
        if manager.connections.get(code,{}).get(pid) is ws:
            manager.connections[code].pop(pid,None)
            if code in manager.rooms: manager.rooms[code].mark_connected(pid,False); await broadcast(code)
