import io
import pycdlib
import yaml
import qemu_lab


def test_seed_has_nocloud_names_keys_and_fixed_management_mac(tmp_path, monkeypatch):
    monkeypatch.setattr(qemu_lab, "STATE", tmp_path)
    (tmp_path / "router").mkdir()
    key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIfixture lab"
    qemu_lab.seed("router", {"mgmt_mac": "52:54:00:20:00:01"}, key)
    iso = pycdlib.PyCdlib()
    iso.open(str(tmp_path / "router/seed.iso"))
    files = {}
    for name in ("user-data", "meta-data", "network-config"):
        output = io.BytesIO()
        iso.get_file_from_iso_fp(output, rr_path="/" + name)
        files[name] = yaml.safe_load(output.getvalue().decode().removeprefix("#cloud-config\n"))
    iso.close()
    assert files["user-data"]["ssh_pwauth"] is False
    assert files["user-data"]["users"][0]["ssh_authorized_keys"] == [key]
    assert files["meta-data"]["instance-id"] == "network-infra-router"
    assert files["network-config"]["ethernets"]["management"]["match"]["macaddress"] == "52:54:00:20:00:01"
