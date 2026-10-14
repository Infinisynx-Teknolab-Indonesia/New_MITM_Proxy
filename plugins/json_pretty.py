"""Action plugin: rapikan / tampilkan JSON response.

Dipanggil manual: HTTP History -> klik-kanan -> Kirim ke Plugin -> Rapikan JSON.
"""
NAME = "Rapikan JSON"
DESCRIPTION = "Tampilkan body response sebagai JSON yang rapi"
MENU = "Rapikan JSON (response)"


def action(ctx):
    import json
    txt = ctx.res_text or ""
    if not txt.strip():
        return "Response body kosong."
    try:
        obj = json.loads(txt)
    except Exception as e:
        return "Body bukan JSON valid:\n" + str(e)
    return json.dumps(obj, indent=2, ensure_ascii=False)
