"""VALANCE 月次人事評価自動化 — エントリーポイント。

使い方:
    python main.py              # 前月分を評価 (デフォルト)
    python main.py --dry-run    # API を叩かずにダミーデータで PDF だけ生成
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from typing import Any

from collectors import calendar as cal_collector
from collectors import drive as drive_collector
from collectors import sheets as sheets_collector
from collectors import slides as slides_collector
from collectors import slack as slack_collector
from config import (
    ACTION_ITEMS_PRESENTATION_ID,
    ACTION_ITEMS_SLIDE_ID,
    GRADE_SHEET_ID,
    KPI_SHEET_ID,
    Config,
    get_evaluation_period,
)
from evaluators.qualitative import evaluate_qualitative
from evaluators.quantitative import score_kpis
from report.pdf_generator import generate_pdf


def main() -> None:
    parser = argparse.ArgumentParser(description="VALANCE 月次評価自動化")
    parser.add_argument("--dry-run", action="store_true", help="ダミーデータで PDF だけ生成")
    args = parser.parse_args()

    cfg = Config()
    errors = cfg.validate()
    if errors and not args.dry_run:
        print("設定エラー:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    period_start, period_end = get_evaluation_period()
    period_label = f"{period_start.year}年{period_start.month}月"

    print(f"=== VALANCE 月次評価 ({period_label}) ===")
    print(f"対象者: {cfg.target_name} ({cfg.target_email})")
    print(f"期間  : {period_start} 〜 {period_end}")
    print()

    if args.dry_run:
        data = _dry_run_data(cfg, period_label)
    else:
        data = _collect_and_evaluate(cfg, period_start, period_end, period_label)

    # PDF 生成
    print("[7/7] PDF 生成中...")
    pdf_path = generate_pdf(data, cfg.output_dir)
    print(f"\n✅ レポート生成完了: {pdf_path}")

    # JSON も保存 (デバッグ・監査用)
    json_path = pdf_path.with_suffix(".json")
    json_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"   JSON: {json_path}")


def _collect_and_evaluate(
    cfg: Config,
    period_start: date,
    period_end: date,
    period_label: str,
) -> dict[str, Any]:
    """全データ収集 → 評価 → レポートデータ構築。"""

    # 1. グレード定義
    print("[1/7] グレード定義を取得中...")
    grade_full = sheets_collector.fetch_grade_definition(cfg.google_sa_file, GRADE_SHEET_ID)
    grade_section = sheets_collector.extract_grade_section(grade_full, cfg.target_grade)

    # 2. KPI (計画 + 実績)
    print("[2/7] KPI データを取得中...")
    kpi_plan = sheets_collector.fetch_kpi_raw_text(
        cfg.google_sa_file, KPI_SHEET_ID, sheet_name="事業計画v001"
    )
    kpi_actual = sheets_collector.fetch_kpi_raw_text(
        cfg.google_sa_file, KPI_SHEET_ID, sheet_name="実績"
    )
    kpi_raw = f"## 事業計画 (年間計画値)\n{kpi_plan}\n\n## 実績 (月次)\n{kpi_actual}"
    # KPI は構造が複雑なので Claude に直接スコアリングさせる
    kpi_scores = {
        "tier1": {"score": None, "details": []},
        "tier2": {"score": None, "details": []},
        "raw_text": kpi_raw,
    }

    # 3. アクションアイテム
    print("[3/7] アクションアイテム (Slides) を取得中...")
    action_items_text = slides_collector.fetch_slide_text(
        cfg.google_sa_file, ACTION_ITEMS_PRESENTATION_ID, ACTION_ITEMS_SLIDE_ID
    )

    # 4. Slack
    print("[4/7] Slack 活動を取得中 (全チャンネル)...")
    try:
        slack_data = slack_collector.fetch_user_messages(
            cfg.slack_bot_token, cfg.target_email, period_start, period_end
        )
        print(f"       → {slack_data.get('total_messages', 0)} メッセージ, "
              f"{slack_data.get('channel_count', 0)} チャンネル")
    except Exception as e:
        print(f"       ⚠️ Slack 取得失敗 (スキップ): {e}")
        slack_data = {"total_messages": 0, "channel_count": 0,
                      "ai_keyword_mentions": 0, "ai_keyword_examples": [],
                      "sample_messages": [], "error": str(e)}

    # 5. Drive
    print("[5/7] Drive ドキュメントを集計中...")
    drive_data = drive_collector.count_documents_created(
        cfg.google_sa_file, cfg.target_email, period_start, period_end, cfg.drive_folder_id
    )
    print(f"       → {drive_data.get('total', 0)} ドキュメント")

    # 6. Calendar
    print("[6/7] カレンダー (MTG) 情報を取得中...")
    calendar_data = cal_collector.fetch_meetings(
        cfg.google_sa_file, cfg.target_calendar_id, period_start, period_end
    )
    print(f"       → {calendar_data.get('total_events', 0)} MTG (NOT 要件)")

    # 定性評価 (Claude)
    print("[6.5/7] Claude による定性評価中...")
    qualitative = evaluate_qualitative(
        api_key=cfg.anthropic_api_key,
        grade_definition=grade_section,
        action_items_text=action_items_text,
        slack_data=slack_data,
        drive_data=drive_data,
        calendar_data=calendar_data,
        kpi_raw_text=kpi_raw,
        target_name=cfg.target_name,
        target_grade=cfg.target_grade,
        period_label=period_label,
    )

    # 総合スコア算出 (a/b も Claude がスコアリング)
    a_score = qualitative.get("a_tier1_kpi", {}).get("score", 50)
    b_score = qualitative.get("b_tier2_kpi", {}).get("score", 50)
    c_score = qualitative.get("c_action_items", {}).get("score", 50)
    d_score = qualitative.get("d_business_qualitative", {}).get("score", 50)
    e_score = qualitative.get("e_ai_and_communication", {}).get("score", 50)

    # KPI スコアを kpi_scores にも反映 (PDF 表示用)
    kpi_scores["tier1"]["score"] = a_score
    kpi_scores["tier1"]["details"] = [{"name": "Tier1 KPI", "rationale": qualitative.get("a_tier1_kpi", {}).get("rationale", "")}]
    kpi_scores["tier2"]["score"] = b_score
    kpi_scores["tier2"]["details"] = [{"name": "Tier2 KPI", "rationale": qualitative.get("b_tier2_kpi", {}).get("rationale", "")}]

    overall = (
        a_score * 0.30
        + b_score * 0.25
        + c_score * 0.20
        + d_score * 0.15
        + e_score * 0.10
    )

    return {
        "target_name": cfg.target_name,
        "target_email": cfg.target_email,
        "target_grade": cfg.target_grade,
        "period_label": period_label,
        "period_start": str(period_start),
        "period_end": str(period_end),
        "grade_definition": grade_section,
        "kpi_scores": kpi_scores,
        "action_items_text": action_items_text,
        "slack_data": slack_data,
        "drive_data": drive_data,
        "calendar_data": calendar_data,
        "qualitative": qualitative,
        "overall_score": round(overall, 1),
        "score_breakdown": {
            "a": {"score": round(a_score, 1), "weighted": round(a_score * 0.30, 1)},
            "b": {"score": round(b_score, 1), "weighted": round(b_score * 0.25, 1)},
            "c": {"score": c_score, "weighted": round(c_score * 0.20, 1)},
            "d": {"score": d_score, "weighted": round(d_score * 0.15, 1)},
            "e": {"score": e_score, "weighted": round(e_score * 0.10, 1)},
        },
    }


def _dry_run_data(cfg: Config, period_label: str) -> dict[str, Any]:
    """ダミーデータでレポートの見た目を確認する。"""
    return {
        "target_name": cfg.target_name or "Kota (dry-run)",
        "target_email": cfg.target_email or "kota@valance.co.jp",
        "target_grade": cfg.target_grade or "役員",
        "period_label": period_label,
        "period_start": "2026-03-01",
        "period_end": "2026-03-31",
        "grade_definition": "役員: 事業全体の数値責任を持ち、組織運営・戦略立案・実行を主導する。",
        "kpi_scores": {
            "tier1": {
                "score": 85.0,
                "details": [
                    {"name": "ARR", "plan": 100_000_000, "actual": 112_000_000, "achievement_rate": 1.12, "score": 89.6},
                    {"name": "売上", "plan": 50_000_000, "actual": 48_000_000, "achievement_rate": 0.96, "score": 76.8},
                ],
            },
            "tier2": {
                "score": 72.0,
                "details": [
                    {"name": "MQL", "plan": 500, "actual": 420, "achievement_rate": 0.84, "score": 67.2},
                    {"name": "churn rate", "plan": 5.0, "actual": 4.2, "achievement_rate": 1.19, "score": 99.0},
                ],
            },
            "raw_text": "(dry-run)",
        },
        "action_items_text": "1. ISMS 認証取得\n2. 新規パートナー 3 社開拓\n3. プロダクト v2 リリース",
        "slack_data": {
            "total_messages": 520,
            "channel_count": 15,
            "ai_keyword_mentions": 34,
            "ai_keyword_examples": ["Claude で分析してみた", "Gemini に聞いてみて"],
            "sample_messages": [],
        },
        "drive_data": {"total": 18, "by_type": {"Google Docs": 8, "Google Slides": 6, "Google Sheets": 4}, "files": []},
        "calendar_data": {"total_events": 72, "organized_count": 25, "events": []},
        "qualitative": {
            "c_action_items": {"score": 78, "rationale": "[dry-run] ISMS 取得完了、パートナー 2/3 社進行中。"},
            "d_business_qualitative": {"score": 82, "rationale": "[dry-run] Slack 投稿量・Drive 成果物ともに高水準。"},
            "e_ai_and_communication": {"score": 70, "rationale": "[dry-run] AI 言及 34 件。積極活用が見られる。"},
            "strengths": ["KPI 達成に向けた実行力", "社内コミュニケーション量の多さ"],
            "improvements": ["MQL パイプラインの底上げ", "AI ツール活用を定常業務に組み込む"],
            "recommended_actions_next_month": [
                "MQL 改善施策を 2 件以上実施",
                "AI ツールの利用を週次で振り返る",
            ],
        },
        "overall_score": 79.1,
        "score_breakdown": {
            "a": {"score": 85.0, "weighted": 25.5},
            "b": {"score": 72.0, "weighted": 18.0},
            "c": {"score": 78, "weighted": 15.6},
            "d": {"score": 82, "weighted": 12.3},
            "e": {"score": 70, "weighted": 7.0},
        },
    }


if __name__ == "__main__":
    main()
