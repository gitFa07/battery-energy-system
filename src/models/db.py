"""SQLite datasheet repository, seeded from the JSON files in `data/datasheets/`.

The JSON files are the source of truth (reviewable in git); SQLite is the query layer the API and workbench read
from. Each category is a table of (id, name, payload JSON); rows come back as validated pydantic models.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from src.config import DATASHEET_DIR
from src.models.schemas import BusbarSpec, CellSpec, CoolingSpec, ModuleDesignInput, ProtectionSpec

M = TypeVar("M", bound=BaseModel)

# table -> (json file, key inside it, model)
CATALOGUE: dict[str, tuple[str, str, type[BaseModel]]] = {
    "cells": ("cells_liiondb.json", "cells", CellSpec),
    "cooling": ("cooling_topologies.json", "cooling", CoolingSpec),
    "busbars": ("busbars_protection.json", "busbars", BusbarSpec),
    "protection": ("busbars_protection.json", "protection", ProtectionSpec),
    "presets": ("presets_three_way.json", "presets", ModuleDesignInput),
}


def load_json(name: str, datasheet_dir: Path = DATASHEET_DIR) -> dict:
    return json.loads((datasheet_dir / name).read_text(encoding="utf-8"))


class DatasheetDB:
    """`DatasheetDB()` is an in-memory store seeded on construction; pass `path` to persist to a file."""

    def __init__(self, path: str | Path = ":memory:", datasheet_dir: Path = DATASHEET_DIR, seed: bool = True):
        self.datasheet_dir = datasheet_dir
        self.conn = sqlite3.connect(str(path))
        for table in (*CATALOGUE, "targets"):
            self.conn.execute(f"CREATE TABLE IF NOT EXISTS {table} "
                              "(id TEXT PRIMARY KEY, name TEXT NOT NULL, payload TEXT NOT NULL)")
        if seed:
            self.seed()

    def seed(self) -> None:
        """(Re)load every table from JSON, validating each row first so a bad file never half-seeds."""
        rows: dict[str, list[tuple[str, str, str]]] = {}
        for table, (file, key, model) in CATALOGUE.items():
            items = [model.model_validate(item) for item in load_json(file, self.datasheet_dir)[key]]
            rows[table] = [(m.id, m.name, m.model_dump_json()) for m in items]
        targets = load_json("presets_three_way.json", self.datasheet_dir)["round1_targets"]
        rows["targets"] = [(pid, pid, json.dumps(t)) for pid, t in targets.items()]
        with self.conn:
            for table, table_rows in rows.items():
                self.conn.execute(f"DELETE FROM {table}")
                self.conn.executemany(f"INSERT INTO {table} VALUES (?, ?, ?)", table_rows)

    def close(self) -> None:
        self.conn.close()

    def _all(self, table: str, model: type[M]) -> list[M]:
        cur = self.conn.execute(f"SELECT payload FROM {table} ORDER BY rowid")
        return [model.model_validate_json(p) for (p,) in cur]

    def _one(self, table: str, model: type[M], id: str) -> M:
        row = self.conn.execute(f"SELECT payload FROM {table} WHERE id = ?", (id,)).fetchone()
        if row is None:
            raise KeyError(f"no {table} entry with id {id!r}")
        return model.model_validate_json(row[0])

    def list_cells(self) -> list[CellSpec]:
        return self._all("cells", CellSpec)

    def get_cell(self, id: str) -> CellSpec:
        return self._one("cells", CellSpec, id)

    def list_cooling(self) -> list[CoolingSpec]:
        return self._all("cooling", CoolingSpec)

    def get_cooling(self, id: str) -> CoolingSpec:
        return self._one("cooling", CoolingSpec, id)

    def list_busbars(self) -> list[BusbarSpec]:
        return self._all("busbars", BusbarSpec)

    def get_busbar(self, id: str) -> BusbarSpec:
        return self._one("busbars", BusbarSpec, id)

    def list_protection(self) -> list[ProtectionSpec]:
        return self._all("protection", ProtectionSpec)

    def get_protection(self, id: str) -> ProtectionSpec:
        return self._one("protection", ProtectionSpec, id)

    def get_presets(self) -> list[ModuleDesignInput]:
        return self._all("presets", ModuleDesignInput)

    def get_targets(self) -> dict[str, dict]:
        """Round-1 target results per preset id (targets to compare against, not model outputs)."""
        cur = self.conn.execute("SELECT id, payload FROM targets ORDER BY rowid")
        return {pid: json.loads(p) for pid, p in cur}
