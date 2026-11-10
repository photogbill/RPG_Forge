"""N7: the dashboard's state, its four actions, and the HTTP guard — on a throwaway world, served on a free port."""
import json, threading, urllib.request, urllib.error

from PIL import Image

from forge import ui, manifest
from test_manifest import make_world, fake_done_job


def test_snapshot_actions_and_http(tmp_path):
    cfg, root, assets = make_world(tmp_path)
    (tmp_path / "jobs" / "paused").mkdir(exist_ok=True)
    manifest.refresh_wanted(cfg, "tg")
    fake_done_job(tmp_path, "J1", "sd_xl_base_1.0.safetensors", outputs=("card.png",))
    (tmp_path / "jobs" / "failed" / "F1.json").write_text(json.dumps({"id": "F1", "type": "render", "name": "x",
        "batch": "b", "error": "ComfyUI down"}), encoding="utf-8")
    (tmp_path / "jobs" / "pending" / "P1.json").write_text(json.dumps({"id": "P1", "type": "render", "batch": "b"}), encoding="utf-8")
    st = ui.State(cfg).snapshot()
    assert st["counts"] == {"pending": 1, "running": 0, "done": 1, "failed": 1, "paused": 0}
    assert st["recent"][0]["image"] == "J1/card.png" and st["failed"][0]["error"] == "ComfyUI down"
    assert any(b["name"] == "b" and b["failed"] == 1 for b in st["batches"])
    assert ui.act(cfg, "pause", {})["ok"] and (tmp_path / "jobs" / "paused" / "P1.json").exists()
    assert ui.act(cfg, "resume", {})["ok"] and (tmp_path / "jobs" / "pending" / "P1.json").exists()
    r = ui.act(cfg, "approve", {"id": "J1", "name": "vignettes/gate_law/01_ribbon", "dry_run": True})
    assert r["ok"] and r["dry_run"] and r["rows"][0]["file"] == "card.png"
    assert Image.open(assets / "vignettes/gate_law/01_ribbon.png").size == (288, 162)     # dry run copied nothing
    bad = ui.act(cfg, "approve", {"id": "J1", "name": "nope/none", "dry_run": True})
    assert not bad["ok"] and "not in" in bad["message"]
    assert ui.act(cfg, "retry", {"id": "F1"})["ok"] and (tmp_path / "jobs" / "pending" / "F1.json").exists()

    srv = ui.make_server(cfg, 0)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        base = f"http://127.0.0.1:{port}"
        assert b"RPG" in urllib.request.urlopen(base + "/").read()
        assert json.loads(urllib.request.urlopen(base + "/api/state").read())["counts"]["done"] == 1
        assert urllib.request.urlopen(base + "/thumb?p=J1/card.png").headers["Content-Type"] == "image/jpeg"
        for bad_path in ("/thumb?p=../jobs/done/J1.json", "/full?p=../../forge.json"):
            try:
                urllib.request.urlopen(base + bad_path)
                assert False, bad_path
            except urllib.error.HTTPError as e:
                assert e.code == 404
        req = urllib.request.Request(base + "/api/act/pause", data=b"{}", method="POST")
        try:
            urllib.request.urlopen(req)
            assert False
        except urllib.error.HTTPError as e:
            assert e.code == 403                                       # no X-Forge header → refused
    finally:
        srv.shutdown()


def test_night3_report_link_kit_check_ab_and_upnext(tmp_path):
    """G9: /report redirects to the newest morning report, /out serves it, kit-check colours reach the card,
    /api/job feeds the A/B view, and the ETA area names what runs next."""
    import urllib.request
    cfg, root, assets = make_world(tmp_path)
    (tmp_path / "jobs" / "paused").mkdir(exist_ok=True)
    fake_done_job(tmp_path, "J1", "sd_xl_base_1.0.safetensors", outputs=("card.png",))
    (tmp_path / "out" / "J1" / "check.json").write_text(json.dumps({"verdict": "warn"}), encoding="utf-8")
    Image.new("RGB", (10, 10)).save(tmp_path / "out" / "J1" / "check.png")
    (tmp_path / "jobs" / "pending" / "P1.json").write_text(json.dumps({"id": "P1", "type": "render", "batch": "late", "priority": 0}), encoding="utf-8")
    (tmp_path / "jobs" / "pending" / "P2.json").write_text(json.dumps({"id": "P2", "type": "render", "batch": "first", "priority": 10}), encoding="utf-8")
    st = ui.State(cfg).snapshot()
    assert st["recent"][0]["check"] == {"verdict": "warn", "image": "J1/check.png"}
    assert st["upcoming"] == ["first", "late"]
    srv = ui.make_server(cfg, 0)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        base = f"http://127.0.0.1:{port}"
        r = urllib.request.urlopen(base + "/report")
        assert r.geturl().startswith(base + "/out/reports/night_") and b"forge overnight" in r.read()
        assert json.loads(urllib.request.urlopen(base + "/api/job?id=J1").read())["id"] == "J1"
        for bad in ("/out/../forge.json", "/out/..%2Fjobs/done/J1.json"):
            try:
                urllib.request.urlopen(base + bad)
                assert False, bad
            except urllib.error.HTTPError as e:
                assert e.code == 404
        assert b"Compare A/B" in urllib.request.urlopen(base + "/").read()
    finally:
        srv.shutdown()
