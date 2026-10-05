# stock-warashibe

株わらしべ計画の研究・運用検証用リポジトリ。

## Current phase

**運用・証拠収集・監視モード**

新規endpointを惰性で増やさず、G6のProspective Shadow evidenceを蓄積しながら、
Runtime / Paper / Shadow / Historical / Evidence Integrity / Burn-in / Recoveryを監視する。

## Active strategy

- champion: `mean_reversion_cost_floor:g6`
- 実売買: なし
- broker接続: なし
- live order: なし
- Paper Gate #037: blocked until forward evidence requirements are met

Prospective Shadowの事前宣言条件:
- 30 observation days
- 20 evaluated buy signals
- Evidence Integrity pass

Historical/Challenger研究はProspective Shadow evidenceから分離し、
Historical結果だけでPaper Gateを開かない。

## Scheduled development path

定時・自動開発の標準変更経路:

ChatGPT
→ Supabase `public.warashibe_dev_queue`
→ GitHub Actions `Stock Warashibe Dev Queue`
→ pytest / `git diff --check`
→ commit / push main
→ explicit `workflow_dispatch`
→ same-SHA CI / Historical / Shadow / Runtime / Paper validation

GitHubへの直接writeは通常のスケジュール開発では原則使用しない。
Queue自身のbootstrap障害など、Queueから自己修復できない場合のみ最小の直接修正を行い、
直後にQueue経路へ戻してprobeで閉ループを再実証する。

## Development supervision

監修判定は以下のいずれか:
- 継続開発
- 修復のみ
- 運用・証拠収集モードへ移行可能

現在は **運用・証拠収集モードへ移行可能** と判定済み。
重大バグ、Gate不整合、証拠汚染、CI閉ループ不全、データ欠損などが出た場合だけ修復開発を再開する。

## Human Gate

以下は自動実行しない:
- 実売買
- broker接続
- 実資金移動
- APIキー / Secrets / 認証情報の変更・新規発行
- 権限拡大
- live order送信
- force push / 不可逆なproduction破壊操作
