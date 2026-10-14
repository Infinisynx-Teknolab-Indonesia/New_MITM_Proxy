"""Plugin contoh: menyisipkan header debug ke setiap request,
dan menandai response dengan header penanda. Aman sebagai template belajar.
"""
NAME = "Contoh: Tambah Header"
DESCRIPTION = "Sisipkan X-Debug ke request & X-Proxy ke response (template)"


def on_request(ctx):
    ctx.set_header("X-Debug", "mini-mitm")


def on_response(ctx):
    ctx.set_header("X-Proxy", "mini-mitm")
