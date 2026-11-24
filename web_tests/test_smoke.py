#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Playwright 真实浏览器冒烟测试（由 wcb-webapp-testing 脚手架生成）。

运行前需安装：
    pip install playwright
    playwright install chromium
"""
import json
import sys
from playwright.sync_api import sync_playwright

TARGET_URL = "http://127.0.0.1:8017"


def main():
    report = {
        "url": TARGET_URL,
        "console_errors": [],
        "page_errors": [],
        "failed_requests": [],
        "http_4xx_5xx": [],
        "assertions_failed": [],
    }
    browser = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            # 铁律① pageerror 抓未捕获异常（最致命盲区）
            page.on("pageerror", lambda exc: report["page_errors"].append(str(exc)))
            # 铁律② console 抓框架级报错
            page.on("console", lambda msg: report["console_errors"].append(msg.text)
                    if msg.type in ("error", "warning") else None)
            # 铁律② requestfailed 抓接口失败
            page.on("requestfailed", lambda req: report["failed_requests"].append(
                req.url + " :: " + str(req.failure)))
            # 4xx/5xx 抓坏接口
            page.on("response", lambda resp: report["http_4xx_5xx"].append(
                resp.url + " :: " + str(resp.status)) if resp.status >= 400 else None)

            page.goto(TARGET_URL, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(1500)

            # 铁律③ 非空断言：真验证而不是只截图
            title = page.title()
            assert title, "页面标题为空，断言失败"
            report["title"] = title

            # 示例交互断言（按被测页面自行扩充）
            try:
                body_text = page.inner_text("body")
                assert body_text.strip(), "页面正文为空，断言失败"
            except Exception as e:
                report["assertions_failed"].append(str(e))

            # 铁律③ 浏览器必须在 finally 关闭，防进程泄漏
            browser.close()
            browser = None
    except Exception as e:
        report["fatal"] = str(e)
        if browser is not None:
            browser.close()
        raise
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass

    ok = (not report["page_errors"] and not report["console_errors"]
          and not report["failed_requests"] and not report["http_4xx_5xx"]
          and not report["assertions_failed"])
    with open("report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
