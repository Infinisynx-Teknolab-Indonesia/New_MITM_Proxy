"""CA sendiri + generate sertifikat per-host untuk MITM.

Jalankan sekali: python ca.py  -> bikin ca/ca.crt dan ca/ca.key
File ca/ca.crt inilah yang harus kamu install sebagai 'trusted CA' di device.
"""
import datetime
import os
import shutil

from paths import BASE_DIR
CA_DIR = os.path.join(BASE_DIR, "ca")
CA_CERT = os.path.join(CA_DIR, "ca.crt")
CA_KEY = os.path.join(CA_DIR, "ca.key")
CERT_CACHE = os.path.join(CA_DIR, "certs")


def _lazy_imports():
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    return x509, NameOID, hashes, serialization, rsa


def ca_pem():
    """Isi sertifikat CA dalam format PEM (bytes)."""
    generate_ca()
    with open(CA_CERT, "rb") as f:
        return f.read()


def ca_der():
    """Isi sertifikat CA dalam format DER (.cer) — berguna untuk iOS."""
    x509, _n, _h, serialization, _r = _lazy_imports()
    cert = x509.load_pem_x509_certificate(ca_pem())
    return cert.public_bytes(serialization.Encoding.DER)


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _save_key(path, key, serialization):
    with open(path, "wb") as f:
        f.write(key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        ))


def generate_ca():
    """Bikin CA root sekali saja. Kalau sudah ada, dilewati."""
    os.makedirs(CERT_CACHE, exist_ok=True)
    if os.path.exists(CA_CERT) and os.path.exists(CA_KEY):
        return

    x509, NameOID, hashes, serialization, rsa = _lazy_imports()
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "MyProxy Root CA"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "MyProxy"),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(_now() - datetime.timedelta(days=1))
        .not_valid_after(_now() + datetime.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                key_cert_sign=True, crl_sign=True, digital_signature=True,
                content_commitment=False, key_encipherment=False,
                data_encipherment=False, key_agreement=False,
                encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )
    _save_key(CA_KEY, key, serialization)
    with open(CA_CERT, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    print(f"[ca] CA dibuat -> install '{CA_CERT}' sebagai trusted CA di device kamu")


def regenerate_ca():
    """Hapus CA lama + semua sertifikat cache, lalu bikin CA baru.
    Setelah ini, CA lama yang terinstal di device TIDAK berlaku lagi -> install ulang ca.crt."""
    if os.path.isdir(CA_DIR):
        shutil.rmtree(CA_DIR, ignore_errors=True)
    os.makedirs(CERT_CACHE, exist_ok=True)
    generate_ca()
    return CA_CERT


def _load_ca():
    x509, NameOID, hashes, serialization, rsa = _lazy_imports()
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    with open(CA_KEY, "rb") as f:
        ca_key = load_pem_private_key(f.read(), password=None)
    with open(CA_CERT, "rb") as f:
        ca_cert = x509.load_pem_x509_certificate(f.read())
    return ca_cert, ca_key


def cert_for_host(hostname):
    """Ambil (atau generate + cache) sertifikat untuk 1 host, ditandatangani CA kita.
    Mengembalikan (path_crt, path_key)."""
    safe = hostname.replace(":", "_").replace("*", "_wild_")
    crt_path = os.path.join(CERT_CACHE, f"{safe}.crt")
    key_path = os.path.join(CERT_CACHE, f"{safe}.key")
    if os.path.exists(crt_path) and os.path.exists(key_path):
        return crt_path, key_path

    x509, NameOID, hashes, serialization, rsa = _lazy_imports()
    ca_cert, ca_key = _load_ca()
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostname)]))
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(_now() - datetime.timedelta(days=1))
        .not_valid_after(_now() + datetime.timedelta(days=825))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(hostname)]), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    _save_key(key_path, key, serialization)
    with open(crt_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    return crt_path, key_path


if __name__ == "__main__":
    generate_ca()
