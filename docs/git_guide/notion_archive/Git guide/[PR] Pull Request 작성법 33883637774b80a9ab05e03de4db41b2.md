# [PR] Pull Request 작성법

```jsx
<!--
PR 제목 규칙: type(scope): description
예) feat(function): add eventhub trigger
-->

## Summary
<!-- 한 줄로: 무엇을 왜 변경했는지 -->
- 

## Changes
<!-- 핵심 변경 2~5개 -->
- 
- 

## Test
<!-- 실행한 테스트/확인 (없으면 N/A) -->
- N/A

## Related
<!-- 이슈 자동 종료: Closes #번호 -->
- Closes #
```

# ✅ Scope

> 변경하는 범위
> 

| 키 | 의미 |
| --- | --- |
| api | API / Endpoint / Controller |
| function | Azure Function |
| pipeline | ETL / 배치 / 데이터 처리 로직 |
| db | DB 스키마 / 쿼리 / 인덱스 |
| infra | Azure 리소스 / IaC / 설정 |
| ci | GitHub Actions / 배포 |
| auth | 인증 / 권한 |
| config | 환경변수 / 설정 파일 |
| refactor | 구조 개선 (기능 변경 없음) |
| docs | 문서 |
| frontend(web) |  |
| frontend(ios) |  |

# **PR 작성 예시**

pr 제목

```jsx
feat(function): add eventhub ingestion trigger
```

Summary

```jsx
- EventHub 수신 데이터 Cosmos 적재 기능 추가
```

Changes

```jsx
- EventHub trigger 함수 구현
- Cosmos upsert 로직 추가
- 기본 예외 처리 추가
```

Related

```jsx
Closes #12
```

이슈 태그하기

![image.png](%5BPR%5D%20Pull%20Request%20%EC%9E%91%EC%84%B1%EB%B2%95/image.png)

Asignee, Reviewer,  Labels 설정 (자동화하면 수동으로 할 필요 X)

![image.png](%5BPR%5D%20Pull%20Request%20%EC%9E%91%EC%84%B1%EB%B2%95/image%201.png)