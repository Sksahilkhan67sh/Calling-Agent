import json
import os
import subprocess
import threading
import urllib.request
import urllib.error
import pathlib
import webhook_receiver

FAKE_TOKEN = "abcdef" * 4
TOOLS = pathlib.Path(__file__).resolve().parents[1] / "tools"


def post(srv, body=b'{"run_id":"1","phone":"+919876543210"}', headers=None):
    req = urllib.request.Request(f"http://127.0.0.1:{srv.server_address[1]}/webhooks/x?tok" + "en=" + FAKE_TOKEN,
                                 data=body, headers=headers or {}, method="POST")
    try:
        return urllib.request.urlopen(req, timeout=5).status
    except urllib.error.HTTPError as e:
        return e.code


def serve(tmp_path, **kw):
    srv = webhook_receiver.make_server("T", out_dir=tmp_path, **kw)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def test_receiver_saves_redacted_capture(tmp_path, monkeypatch):
    monkeypatch.setenv("DOGRAH_WEBHOOK_HEADER_NAME", "X-Hook-Secret")
    srv = serve(tmp_path)
    assert post(srv, headers={"X-Hook-Secret": "supersecretvalue", "Content-Type": "application/json"}) == 200
    srv.shutdown()
    text = next((tmp_path / "T").glob("*.json")).read_text()
    assert "supersecretvalue" not in text and "+919876543210" not in text and FAKE_TOKEN not in text
    assert json.loads(text)["seq"] == 1


def test_fail_then_ok_mode(tmp_path):
    srv = serve(tmp_path, mode="fail_then_ok", fail_count=1)
    assert [post(srv), post(srv)] == [500, 200]
    srv.shutdown()


def run_scan(path):
    return subprocess.run([str(TOOLS / "secret_scan.sh"), str(path)], capture_output=True, text=True,
                          env={**os.environ, "SPIKE_TEST_NUMBERS": ""})


def test_scan_catches_planted_token_and_passes_clean(tmp_path):
    clean = tmp_path / "clean"
    clean.mkdir()
    (clean / "a.md").write_text("nothing secret here\n")
    assert run_scan(clean).returncode == 0
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "b.txt").write_text("key = " + "github_pat_" + "A" * 30 + "\n")
    out = run_scan(bad)
    assert out.returncode == 1 and "token pattern" in out.stdout


def test_scan_catches_raw_folder_and_unmasked_phone(tmp_path):
    (tmp_path / "x" / "raw").mkdir(parents=True)
    (tmp_path / "x" / "raw" / "f.json").write_text("{}")
    assert run_scan(tmp_path / "x").returncode == 1
    (tmp_path / "y").mkdir()
    (tmp_path / "y" / "n.md").write_text("call +" + "91" + "9876543210\n")
    assert run_scan(tmp_path / "y").returncode == 1
