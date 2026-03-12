from fastapi import FastAPI, WebSocket
from pydantic import BaseModel
from typing import List, Dict
import json

app = FastAPI()

class Vehicle(BaseModel):
    id: str
    type: str
    status: str
    location: Dict[str, float]

class FleetManager:
    def __init__(self):
        self.vehicles: List[Vehicle] = []
    
    def add_vehicle(self, vehicle: Vehicle):
        self.vehicles.append(vehicle)
    
    def get_fleet_status(self):
        return [vehicle.dict() for vehicle in self.vehicles]

fleet_manager = FleetManager()

@app.websocket("/ws/fleet")
async def fleet_websocket(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            vehicle = Vehicle(**json.loads(data))
            fleet_manager.add_vehicle(vehicle)
            await websocket.send_text(json.dumps({
                "status": "Vehicle added",
                "fleet_size": len(fleet_manager.vehicles)
            }))
    except Exception as e:
        print(f"WebSocket error: {e}")

@app.get("/fleet/status")
async def get_fleet_status():
    return fleet_manager.get_fleet_status()