-- =============================================================================
-- SENSE Gold Layer — Seed Data
-- 참조: docs/data_dict/SENSE 데이터 사전.md § 차원 테이블
--
-- 실행 순서: gold_layer_ddl.sql 실행 후 실행
-- 재실행 안전: INSERT ON CONFLICT DO NOTHING
-- =============================================================================


-- =============================================================================
-- § 1. gold_equity.dim_equity — 주가 종목 마스터
-- =============================================================================
INSERT INTO gold_equity.dim_equity (ticker, name_kr, name_en, market, asset_type, role)
VALUES
    -- 예측 타겟 (downside / upside 분류)
    ('005930.KS', '삼성전자',   'Samsung Electronics', 'KOSPI',  'stock', 'target'),
    ('000660.KS', 'SK하이닉스', 'SK Hynix',            'KOSPI',  'stock', 'target'),

    -- 글로벌 Leading 지표
    ('NVDA',      NULL,         'NVIDIA',              'NASDAQ', 'stock',   'leading'),
    ('AMD',       NULL,         'AMD',                 'NASDAQ', 'stock',   'leading'),
    ('MU',        NULL,         'Micron Technology',   'NASDAQ', 'stock',   'leading'),
    ('TSM',       NULL,         'TSMC ADR',            'NYSE',   'stock',   'leading'),
    ('ASML',      NULL,         'ASML Holding',        'NASDAQ', 'stock',   'leading'),
    ('^SOX',      NULL,         'PHLX Semiconductor',  'NASDAQ', 'index',   'leading'),
    ('SOXL',      NULL,         'Direxion 3x SOX ETF', 'NASDAQ', 'etf',     'leading')
ON CONFLICT (ticker) DO NOTHING;


-- =============================================================================
-- § 2. gold_macro.dim_macro_metadatas — 매크로 시계열 메타
-- =============================================================================
INSERT INTO gold_macro.dim_macro_metadatas (ticker, display_name, category, unit, data_source)
VALUES
    -- 원자재
    ('CL=F',            'WTI 원유',         'commodity', 'USD/barrel',  'yahoo_finance'),
    ('GC=F',            'Gold',             'commodity', 'USD/troy oz', 'yahoo_finance'),

    -- 달러 지수
    ('DX-Y.NYB',        'DXY Dollar Index', 'currency',  'index',       'yahoo_finance'),

    -- FRED 금리 시리즈
    ('DGS10',           'US 10Y Treasury',  'bond',      '%',           'fred'),
    ('DGS2',            'US 2Y Treasury',   'bond',      '%',           'fred'),
    ('T10Y2Y',          'Yield Spread 10-2','bond',      '%',           'fred'),
    ('DFF',             'Fed Funds Rate',   'bond',      '%',           'fred'),
    ('DFII10',          '10Y TIPS',         'bond',      '%',           'fred'),
    ('BAMLH0A0HYM2',    'HY OAS Spread',    'bond',      'bps',         'fred')
ON CONFLICT (ticker) DO NOTHING;
