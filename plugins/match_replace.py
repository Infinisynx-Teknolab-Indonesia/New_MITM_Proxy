"""Plugin contoh: Match & Replace (ganti teks otomatis di body response),
mirip fitur Match/Replace di Burp. Edit daftar RULES sesuai kebutuhan.
"""
NAME = "Contoh: Match & Replace"
DESCRIPTION = "Ganti teks pada body response secara otomatis"

# (cari, ganti) — berlaku untuk body response berbentuk teks
RULES = [
    ("\"premium\": false", "\"premium\": true"),
]


def on_response(ctx):
    t = ctx.text
    if not t:
        return
    changed = False
    for find, repl in RULES:
        if find in t:
            t = t.replace(find, repl)
            changed = True
    if changed:
        ctx.text = t
