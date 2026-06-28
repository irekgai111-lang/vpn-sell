# Graph Report - bot  (2026-06-28)

## Corpus Check
- 6 files · ~4,717 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 118 nodes · 234 edges · 17 communities (8 shown, 9 thin omitted)
- Extraction: 100% EXTRACTED · 0% INFERRED · 0% AMBIGUOUS
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `f6c5972f`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]

## God Nodes (most connected - your core abstractions)
1. `_conn()` - 30 edges
2. `_h()` - 8 edges
3. `is_admin()` - 5 edges
4. `cmd_start()` - 5 edges
5. `cb_buy()` - 5 edges
6. `cb_pay()` - 5 edges
7. `cb_ref()` - 5 edges
8. `cb_back()` - 5 edges
9. `cb_promo()` - 5 edges
10. `handle_promo_text()` - 5 edges

## Surprising Connections (you probably didn't know these)
- `main_kb()` --references--> `IKM`  [EXTRACTED]
  bot.py →   _Bridges community 4 → community 1_
- `cb_pay_stars()` --references--> `Update`  [EXTRACTED]
  bot.py →   _Bridges community 1 → community 8_
- `cmd_adddays()` --references--> `Update`  [EXTRACTED]
  bot.py →   _Bridges community 1 → community 6_
- `pre_checkout()` --references--> `Update`  [EXTRACTED]
  bot.py →   _Bridges community 1 → community 9_
- `successful_payment()` --references--> `Update`  [EXTRACTED]
  bot.py →   _Bridges community 1 → community 10_

## Import Cycles
- None detected.

## Communities (17 total, 9 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.16
Nodes (23): active_count(), add_payment(), add_referral(), can_invoice(), _conn(), deactivate_expired(), get_active_sub(), get_pending() (+15 more)

### Community 1 - "Community 1"
Cohesion: 0.25
Nodes (17): cb_check(), cb_howto(), cb_mysub(), cb_pay(), cb_plan(), cb_promo(), cb_support(), cb_trial() (+9 more)

### Community 2 - "Community 2"
Cohesion: 0.23
Nodes (13): datetime, create_user(), delete_user(), get_links(), get_traffic(), _h(), panel_stats(), Marzban VPN Panel API клиент. (+5 more)

### Community 3 - "Community 3"
Cohesion: 0.22
Nodes (11): AsyncIOScheduler, Bot, check_payments(), cleanup(), _deliver_key(), Фоновые задачи (запускаются внутри процесса бота):   • check_payments — каждые 3, Уведомления об истечении подписки: за 3д, 1д, в день X, и реактивация через 3д., Отправляет VPN-ключ клиенту после оплаты. (+3 more)

### Community 4 - "Community 4"
Cohesion: 0.26
Nodes (9): cb_back(), cb_buy(), cb_ref(), cmd_start(), main_kb(), main_text(), plan_text(), VPN Sales Bot v2 — полная автоматизация продаж Оплата: Telegram Stars + YooKassa (+1 more)

### Community 5 - "Community 5"
Cohesion: 0.28
Nodes (8): check_payment(), crypto_check(), crypto_create(), Платёжные провайдеры: CryptoBot (USDT) + YooKassa (карты/СБП)., Возвращает {"invoice_id": str, "pay_url": str}, Возвращает {"invoice_id": str, "pay_url": str}, yk_check(), yk_create()

### Community 6 - "Community 6"
Cohesion: 0.25
Nodes (8): cmd_adddays(), cmd_broadcast(), cmd_promo(), cmd_stat(), is_admin(), Добавить дни подписке: /adddays <tg_id> <days>, Рассылка: /broadcast <текст>, /promo CODE DISCOUNT_PCT [USES] — создать промокод. USES=-1 безлимит.

### Community 7 - "Community 7"
Cohesion: 0.67
Nodes (3): add_subscription(), extend_or_add(), Продлевает активную подписку. Если нет — создаёт новую.

## Knowledge Gaps
- **9 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `_conn()` connect `Community 0` to `Community 7`, `Community 11`, `Community 12`, `Community 13`, `Community 14`, `Community 15`, `Community 16`?**
  _High betweenness centrality (0.046) - this node is a cross-community bridge._
- **What connects `VPN Sales Bot v2 — полная автоматизация продаж Оплата: Telegram Stars + YooKassa`, `Карта (YooKassa) и крипта (CryptoBot).`, `Telegram Stars — нативная оплата внутри Telegram.` to the rest of the system?**
  _30 weakly-connected nodes found - possible documentation gaps or missing edges._