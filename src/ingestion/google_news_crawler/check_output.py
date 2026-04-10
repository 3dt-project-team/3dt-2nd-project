import json

for kw in ["SK_Hynix", "Samsung_Electronics"]:
    records = []
    try:
        with open(f"data/output/{kw}_news.json", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        with_body = [r for r in records if r.get("body")]
        body_lens = [len(r["body"]) for r in with_body]
        avg_len = sum(body_lens) // len(body_lens) if body_lens else 0
        rate = 100 * len(with_body) // len(records) if records else 0
        print(f"=== {kw} ===")
        print(f"  전체: {len(records)}건")
        print(f"  본문 있음: {len(with_body)}건 ({rate}%)")
        print(f"  본문 없음: {len(records) - len(with_body)}건")
        print(f"  평균 본문 길이: {avg_len}자")
        if records:
            print(f"  샘플 헤드라인: {records[0]['headline'][:70]}")
            print(f"  샘플 본문: {(records[0].get('body') or '')[:120]}")
        print()
    except FileNotFoundError:
        print(f"{kw}: 파일 없음\n")
