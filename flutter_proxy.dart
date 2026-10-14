// flutter_proxy.dart
//
// Membuat aplikasi Flutter MILIKMU bisa di-intercept oleh Mini MITM Proxy.
// Flutter TIDAK mengikuti proxy device dan punya CA store sendiri, jadi cara
// paling andal adalah mengarahkan trafik dari dalam kode (khusus build DEBUG).
//
// >>> HANYA untuk pengembangan/debug. JANGAN dipakai di rilis produksi. <<<
// badCertificateCallback => true berarti semua sertifikat diterima (tidak aman
// untuk end-user), tapi itulah yang membuat proxy bisa membaca HTTPS.
//
// Cara pakai:
// 1. Jalankan Mini MITM Proxy di laptop. Cari IP laptop (cmd: ipconfig -> IPv4).
// 2. Pastikan HP dan laptop satu jaringan Wi-Fi.
// 3. Taruh file ini di lib/ dan panggil di main() SEBELUM runApp:
//
//      import 'flutter_proxy.dart';
//      void main() {
//        // 8080 = port proxy. Ganti IP sesuai laptop kamu.
//        enableDebugProxy('192.168.1.5', 8080);
//        runApp(const MyApp());
//      }
//
//    Supaya hanya aktif di debug, bisa pakai kDebugMode:
//      import 'package:flutter/foundation.dart';
//      if (kDebugMode) enableDebugProxy('192.168.1.5', 8080);
//
// Ini bekerja untuk dart:io HttpClient, package:http (IOClient), dan dio
// (IOHttpClientAdapter) karena semuanya memakai HttpClient global.

import 'dart:io';

class _ProxyHttpOverrides extends HttpOverrides {
  final String host;
  final int port;
  _ProxyHttpOverrides(this.host, this.port);

  @override
  HttpClient createHttpClient(SecurityContext? context) {
    final client = super.createHttpClient(context);
    client.findProxy = (uri) => 'PROXY $host:$port;';
    // Terima sertifikat dari proxy (MITM). Debug saja!
    client.badCertificateCallback =
        (X509Certificate cert, String host, int port) => true;
    return client;
  }
}

void enableDebugProxy(String host, int port) {
  HttpOverrides.global = _ProxyHttpOverrides(host, port);
}
