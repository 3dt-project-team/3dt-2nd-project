from __future__ import annotations

import json
from typing import Any

from .schemas import RetrievalBundle

SYSTEM_PROMPT = """
당신은 SENSE(Semiconductor Economic, News & Signal Engine)의 RAG 분석 어시스턴트다.

반드시 지켜야 할 규칙:
1. 제공된 컨텍스트만 근거로 답한다.
2. 뉴스 근거와 정량 지표를 구분해서 설명한다.
3. 근거가 부족하면 부족하다고 명시한다.
4. 투자 추천처럼 단정하지 말고, 관측과 해석을 분리한다.
5. 기사 제목, 날짜, 언론사, 정량 지표를 가능한 한 답변에 반영한다.
6. 출력은 짧고 명확하게 하되, 핵심 근거는 빠뜨리지 않는다.

권장 출력 형식:
[한줄 결론]
...

[시장 해석]
...

[핵심 근거]
1. ...
2. ...

[근거 기사]
- 제목 | 날짜 | 언론사
- 제목 | 날짜 | 언론사

[주의할 점]
- ...
""".strip()


def _dump_rows(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "없음"
    return json.dumps(rows, ensure_ascii=False, indent=2, default=str)


def _render_news_docs(news_docs: list[dict[str, Any]]) -> str:
    if not news_docs:
        return "없음"

    lines: list[str] = []
    for idx, doc in enumerate(news_docs, start=1):
        lines.append(
            "\n".join(
                [
                    f"[{idx}]",
                    f"- 제목: {doc.get('display_title', '-')}",
                    f"- 요약: {doc.get('core_summary', '-')}",
                    f"- 감성: {doc.get('sentiment_class', '-')}",
                    f"- 카테고리: {doc.get('category', '-')}",
                    f"- 언론사: {doc.get('press', '-')}",
                    f"- 종목 키워드: {doc.get('stock_keyword', '-')}",
                    f"- 날짜: {doc.get('pub_date', '-')}",
                    f"- aspect_tag: {doc.get('aspect_tag', '-')}",
                    f"- feature_score: {doc.get('feature_score', '-')}",
                    f"- hybrid_score: {doc.get('hybrid_score', '-')}",
                    f"- 본문 컨텍스트: {doc.get('search_context', '-')}",
                    f"- URL: {doc.get('original_url', '-')}",
                ]
            )
        )
    return "\n\n".join(lines)


def build_user_prompt(bundle: RetrievalBundle) -> str:
    return f"""
질문:
{bundle.question}

질의 라우트:
{bundle.route.value}

질의 필터:
{_dump_rows([bundle.filters.to_dict()])}

최신 예측:
{_dump_rows(bundle.forecast_rows)}

최신 매크로 스냅샷:
{_dump_rows(bundle.macro_snapshot)}

최근 매크로 추이:
{_dump_rows(bundle.macro_trend)}

최신 ML 피처 스냅샷:
{_dump_rows(bundle.ml_feature_snapshot)}

최신 정량 신호:
{_dump_rows(bundle.quant_signal_rows)}

최신 뉴스 감성 스냅샷:
{_dump_rows(bundle.sentiment_snapshot)}

최근 뉴스 감성 추이:
{_dump_rows(bundle.sentiment_trend)}

모델 비교:
{_dump_rows(bundle.model_comparison_rows)}

근거 기사 후보:
{_render_news_docs(bundle.news_docs)}
""".strip()


def render_context_snapshot(bundle: RetrievalBundle) -> str:
    lines = [
        "[LLM 응답 없이도 확인 가능한 컨텍스트 요약]",
        f"- route: {bundle.route.value}",
        f"- stock: {bundle.filters.stock_keyword or 'all'}",
        f"- retrieved_news: {len(bundle.news_docs)}건",
    ]

    if bundle.forecast_rows:
        forecast = bundle.forecast_rows[0]
        lines.append(
            "- 최근 예측: "
            f"{forecast.get('ticker')} / horizon {forecast.get('horizon_day')}일 / "
            f"confidence {forecast.get('confidence_score')}"
        )

    if bundle.macro_snapshot:
        macro = bundle.macro_snapshot[0]
        lines.append(
            "- 최근 매크로: "
            f"USD/KRW {macro.get('usd_krw_rate')}, "
            f"DGS10 {macro.get('fred_dgs10')}, "
            f"Risk-off {macro.get('risk_off_flag')}"
        )

    if bundle.ml_feature_snapshot:
        ml = bundle.ml_feature_snapshot[0]
        lines.append(
            "- 최근 ML 피처: "
            f"sox_return_1d {ml.get('sox_return_1d')}, "
            f"avg_absa_score {ml.get('avg_absa_score')}, "
            f"downside_flag {ml.get('downside_flag')}"
        )

    if bundle.quant_signal_rows:
        quant = bundle.quant_signal_rows[0]
        lines.append(
            "- 최근 퀀트: "
            f"SOX 1d {quant.get('sox_return_1d')}, "
            f"PCR {quant.get('pcr_ratio')}, "
            f"memory trend {quant.get('memory_trend_flag')}"
        )

    if bundle.news_docs:
        lines.append("[근거 기사]")
        for doc in bundle.news_docs[:3]:
            lines.append(
                f"- {doc.get('display_title')} | {doc.get('pub_date')} | {doc.get('press')}"
            )

    return "\n".join(lines)
