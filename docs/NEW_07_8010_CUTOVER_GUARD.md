# NEW-07：8010切换脚本执行保护

本任务只修补和验证脚本，没有切换服务。8000不属于本脚本允许范围。

## 默认调用

下列调用只输出预检说明，不读取或修改配置，不停止或启动服务，也不写运行报告：

```powershell
python -m scripts.run_v2_6_2_8010_cutover
python -m scripts.run_v2_6_2_8010_rollback_drill
```

## 未来受控执行条件

真正执行时必须同时提供：

- `--execute`
- `--target-port 8010`
- `--expected-candidate-hash <完整候选哈希>`
- `--authorization-file <本次Owner授权JSON>`

授权JSON必须包含与manifest一致的`candidate_hash`、可追踪的`decision_id`或`authorization_id`，以及对应动作的布尔权限：

- 持续切换：`port_8010_persistent_primary_switch_authorized: true`
- T6回滚演练：`port_8010_rollback_drill_authorized: true`

脚本中的说明文字、历史报告和旧授权记录不能代替本次授权文件。当前“候选批准、未部署”决定不包含上述持续切换权限，因此不能用于执行。

示例结构：

```json
{
  "decision_id": "OWNER-DECISION-ID",
  "candidate_hash": "FULL_CANDIDATE_HASH",
  "port_8010_persistent_primary_switch_authorized": true
}
```

## 执行保护

进入任何配置写入或restart之前，脚本会核对：

1. 目标端口只能是8010。
2. 配置起点必须为`V1_PRIMARY`。
3. manifest、命令行候选哈希与授权文件候选哈希完全一致。
4. 授权文件明确允许本次动作。
5. 8000没有监听。

执行前记录配置SHA、配置字节、8010是否运行及授权文件SHA。执行失败时恢复原配置字节；8010原本运行则恢复运行，原本停止则保持停止。恢复失败会写成`FAIL_RECOVERY_FAILED`，不会宣称已恢复。

## 报告解释

- `PRECHECK_ONLY_NO_CHANGES`：默认调用，没有写入或重启。
- `PASS_ACTIVE_V262`：持续切换成功，8010保持候选主答。
- `FAIL_RESTORED_PRE_EXECUTION_STATE`：执行失败，已恢复到执行前配置和进程状态。
- `FAIL_RECOVERY_FAILED`：执行和恢复均未完全成功，必须人工检查现场。
