"""Terjemahan antarmuka (Indonesia / English / 中文).

Dipakai untuk teks utama (tab, toolbar, status, beberapa tombol).
Bahasa disimpan di settings (config), diterapkan saat aplikasi dijalankan ulang.
"""
import config

_T = {
    "id": {
        "tab_intercept": "  Intercept  ", "tab_history": "  HTTP History  ",
        "tab_repeater": "  Repeater  ", "tab_intruder": "  Intruder  ",
        "tab_jwt": "  JWT  ", "tab_airunner": "  AI Runner  ", "tab_plugins": "  Plugins  ",
        "start": "▶ Start", "stop": "■ Stop",
        "intercept_on": "Intercept: ON", "intercept_off": "Intercept: OFF",
        "hold_response": "juga tahan Response", "forward_all": "Forward semua (skip)",
        "browser": "\U0001F310 Browser", "settings": "⚙ Settings",
        "running": "● Running", "stopped": "● Stopped",
        "proxy": "Proxy", "upstream": "Upstream", "direct": "langsung",
        "plugins_active": "Plugin aktif", "held": "ditahan",
        "clients": "Klien (dari User-Agent)", "all": "Semua",
        "language": "Bahasa (perlu restart)",
    },
    "en": {
        "tab_intercept": "  Intercept  ", "tab_history": "  HTTP History  ",
        "tab_repeater": "  Repeater  ", "tab_intruder": "  Intruder  ",
        "tab_jwt": "  JWT  ", "tab_airunner": "  AI Runner  ", "tab_plugins": "  Plugins  ",
        "start": "▶ Start", "stop": "■ Stop",
        "intercept_on": "Intercept: ON", "intercept_off": "Intercept: OFF",
        "hold_response": "also hold Response", "forward_all": "Forward all (skip)",
        "browser": "\U0001F310 Browser", "settings": "⚙ Settings",
        "running": "● Running", "stopped": "● Stopped",
        "proxy": "Proxy", "upstream": "Upstream", "direct": "direct",
        "plugins_active": "Plugins active", "held": "held",
        "clients": "Clients (by User-Agent)", "all": "All",
        "language": "Language (restart needed)",
    },
    "zh": {
        "tab_intercept": "  拦截  ", "tab_history": "  HTTP 历史  ",
        "tab_repeater": "  重放  ", "tab_intruder": "  入侵者  ",
        "tab_jwt": "  JWT  ", "tab_airunner": "  AI 运行  ", "tab_plugins": "  插件  ",
        "start": "▶ 开始", "stop": "■ 停止",
        "intercept_on": "拦截: 开", "intercept_off": "拦截: 关",
        "hold_response": "同时拦截响应", "forward_all": "全部放行",
        "browser": "\U0001F310 浏览器", "settings": "⚙ 设置",
        "running": "● 运行中", "stopped": "● 已停止",
        "proxy": "代理", "upstream": "上游", "direct": "直连",
        "plugins_active": "启用插件", "held": "待处理",
        "clients": "客户端 (按 User-Agent)", "all": "全部",
        "language": "语言 (需重启)",
    },
}

LANGS = [("id", "Indonesia"), ("en", "English"), ("zh", "中文")]


def lang():
    return config.get().get("lang", "id")


def t(key):
    code = lang()
    return _T.get(code, _T["id"]).get(key, _T["id"].get(key, key))
