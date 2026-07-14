"""Testovi NIKAD ne diraju stvarnu bazu — preusmjeri na privremenu PRIJE importa appa.
(env var ima prednost pred .env u pydantic-settings)"""
import os, tempfile, pathlib

_tmp = pathlib.Path(tempfile.mkdtemp(prefix="wms_test_")) / "test.db"
os.environ["DATABASE_URL"] = "sqlite:///" + str(_tmp).replace("\\", "/")
os.environ["ADMIN_PASSWORD"] = "admin"
os.environ["ERP_ADAPTER"] = "mock"
