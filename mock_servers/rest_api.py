"""Mock Pet Store REST API server for testing REST virtualization."""

from __future__ import annotations

import argparse

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Pet Store API", version="1.0.0")

# In-memory store
PETS: dict[int, dict] = {
    1: {"id": 1, "name": "Buddy", "species": "dog", "age": 3},
    2: {"id": 2, "name": "Whiskers", "species": "cat", "age": 5},
    3: {"id": 3, "name": "Nemo", "species": "fish", "age": 1},
}
_next_id = 4


class PetInput(BaseModel):
    name: str
    species: str
    age: int | None = None


@app.get("/pets")
async def list_pets(species: str | None = None, limit: int = 10) -> dict:
    pets = list(PETS.values())
    if species:
        pets = [p for p in pets if p["species"] == species]
    return {"pets": pets[:limit], "total": len(pets)}


@app.post("/pets", status_code=201)
async def create_pet(pet: PetInput) -> dict:
    global _next_id
    new_pet = {"id": _next_id, "name": pet.name, "species": pet.species, "age": pet.age}
    PETS[_next_id] = new_pet
    _next_id += 1
    return new_pet


@app.get("/pets/{pet_id}")
async def get_pet(pet_id: int) -> dict:
    if pet_id not in PETS:
        raise HTTPException(status_code=404, detail=f"Pet {pet_id} not found")
    return PETS[pet_id]


@app.delete("/pets/{pet_id}", status_code=204)
async def delete_pet(pet_id: int) -> None:
    if pet_id not in PETS:
        raise HTTPException(status_code=404, detail=f"Pet {pet_id} not found")
    del PETS[pet_id]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mock Pet Store REST API")
    parser.add_argument("--port", type=int, default=9003)
    args = parser.parse_args()
    uvicorn.run(app, host="0.0.0.0", port=args.port)
