# 双站试验归档交换室

材料试验中心的缺块清点岗提交归档清册，各站值守岗登记当班剩余额度。白班固定清册与站图版本，先在线核对，再发行两份站件。夜班把实际收到的站件存入独立实收库，源站维护期间按两个指定实收号签出可以同时补传的块数。交接下一班时，以报告号领取当时的结论及其两份实收出处。

## 一天的交班

1. 清点岗交来缺块行。每行包含唯一的 `block_id`，可附 `locator`。清册保留输入行号及定位符。
2. 链路值守岗按站登记具名端口、任务端点与有向链路，拿到固定站图修订。
3. 白班冻结待补传清册及两个站图修订，拿到批次修订键。
4. 白班在线核算全网容量，分别发行两站的固定 V1 站件。传递缺件时按发行号补发原字节。
5. 夜班核验并实收站件。重投完整原件时复领原首执。
6. 源库下线后，夜班用两份指定实收签报。值班员依据已签存的块数安排补传。
7. 次班收到更正，冻结新修订并沿同一入口发行、实收和签报。
8. 重开夜班库，按旧、新报告号领取各班原结论、出处及回执。

## 运行

在工程根目录使用 Python 3.11 标准库。运行控制台提供的完整回归入口和正常演示。

```text
python3 -B check_project.py
python3 -B demo.py
```

`python3 -B -m unittest discover -s tests -t .` 可直接发现原套件。`samples/shift.json` 是演示的源侧清册和站网输入。演示中三块待补传数据先签一块，更正链路后签两块。每次签报都在关闭并移走源库后进行。测试另覆盖独享与共用链路、三口回站接力、合法零容量、混配、坏件和提交拒绝。

## Python 接口

调用方管理三个独立的 `sqlite3.Connection`。源库连接用于 `StationRevisionStore`、`BatchStore` 和 `IssueRegistry`，夜班实收库用于 `ReceiptStore`，报告库用于 `ReportArchive`。打开连接后调用各对象的 `initialize()`。源库可按上列顺序初始化。初始化及写操作使用没有待提交事务的连接。业务写入口负责自己的提交和回滚，重复初始化保留已写数据。

| 入口 | 调用与结果 |
| --- | --- |
| `station.topology.build_station_graph` | `(site, terminal, nodes, links, ports)` 构造站图。`links` 是 `DirectedLink` 序列，`ports` 是 `PortBinding` 序列。 |
| `station.revisions.StationRevisionStore.register` | `(graph)` 追加固定站图并返回 `GraphRevisionId`。 |
| `batch.freeze.freeze_batch` | `(batches, stations, batch_id, rows, sender, receiver)` 返回 `BatchRevisionId`。`rows` 为清册映射行，`sender` 和 `receiver` 为不同站的已登记站图修订。 |
| `station.online_check.online_check` | `(batches, stations, key)` 返回整数块数。 |
| `issue.publish.issue_station` | `(batches, stations, registry, key, site)` 返回已登记件的 `bytes`。可用 `issue.envelope.decode_v1` 读取发行号。 |
| `issue.reissue.reissue_station` | `(registry, issue_id)` 返回登记的原 `bytes`。 |
| `receive.admit.accept_piece` | `(receipts, raw)` 返回含 `receipt_id`、`first_ack` 和固定站件的 `Receipt`。 |
| `report.sign.sign_capacity` | `(receipts, archive, first_id, second_id)` 返回 `StoredReport`。参数可以按任一站序传入，报告按发送站、接收站保存出处。 |
| `report.readback.read_report` | `(archive, report_id)` 返回原签存 `StoredReport`。 |

站名、节点名、端口名和块名为非空字符串，按原值精确匹配。本站端口名唯一，多个端口可绑定同一节点，端口也可绑定任务端点。两站在线核算和离线签报要求端口名称集合相同，空集合允许。容量为非负整数块数。平行链路各自提供容量。流量在任务端点之外守恒，每个共享口两边的净流量相抵。全网最大整数流量按清册块数封顶，空清册及不可达均签零。工程面向有限数目的交接口，发行计算量随交接口数增加。

V1 外层固定 `version`、`issue_id`、`body` 和 `digest`。站件以规范 JSON 字节传递，摘要覆盖版本、发行号及正文。正文的共用上下文包含批次名称、冻结修订与冻结身份、本站及任务双方、需求和端口名称，站内容量依据随件携带。源库保存原始清册、站内节点和链路。实收先校验信封与共用上下文，签报再解释容量依据。

非法清册、未知容量修订、错批配对和非法容量证据报 `ValueError` 或其子类。坏件报 `PieceValidationError`，有效同号异内容报 `ReceiptConflict`。未知冻结修订、发行号、实收号或报告号按 `KeyError` 或其子类报告。数据库拒绝写入或提交时传播 SQLite 异常，无本次成功返回。报告的 `origins` 固定保存两份实际实收的编号、发行号、站别和完整冻结身份，历史领取读取持久存值。
