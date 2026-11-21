"""示例数据：反映真实多维分析平台的业务指标、OLAP立方、分群和分析配置。"""

from __future__ import annotations

from typing import Any

SEED_ROWS: dict[str, list[dict[str, Any]]] = {
    # ---- 指标体系 ----
    "metric_def": [
        {
            "id": 1, "status": "已发布", "pending": False, "abnormal": False,
            "指标编码": "DAU", "指标名称": "日活跃用户数",
            "业务域": "用户增长", "计算口径": "当日至少有一次访问行为的独立设备数",
            "聚合函数": "DISTINCT_COUNT", "数据粒度": "按日", "是否可累加": "否",
        },
        {
            "id": 2, "status": "已发布", "pending": False, "abnormal": False,
            "指标编码": "GMV", "指标名称": "交易总额",
            "业务域": "营收分析", "计算口径": "所有已完成订单的实付金额之和",
            "聚合函数": "SUM", "数据粒度": "按日/按小时", "是否可累加": "是",
        },
        {
            "id": 3, "status": "已发布", "pending": False, "abnormal": False,
            "指标编码": "ARPU", "指标名称": "每用户平均收入",
            "业务域": "营收分析", "计算口径": "GMV/DAU",
            "聚合函数": "AVG", "数据粒度": "按日", "是否可累加": "否",
        },
        {
            "id": 4, "status": "已审核", "pending": True, "abnormal": False,
            "指标编码": "CONV_RATE", "指标名称": "转化率",
            "业务域": "增长漏斗", "计算口径": "完成目标行为的用户数/进入漏斗的用户数",
            "聚合函数": "AVG", "数据粒度": "按周", "是否可累加": "否",
        },
        {
            "id": 5, "status": "已发布", "pending": False, "abnormal": False,
            "指标编码": "RET_7D", "指标名称": "7日留存率",
            "业务域": "用户增长", "计算口径": "新用户注册后第7日仍活跃的比例",
            "聚合函数": "AVG", "数据粒度": "按周", "是否可累加": "否",
        },
        {
            "id": 6, "status": "草稿", "pending": True, "abnormal": False,
            "指标编码": "LTV_30D", "指标名称": "30日用户生命周期价值",
            "业务域": "营收分析", "计算口径": "新用户注册后30天内的累计GMV",
            "聚合函数": "SUM", "数据粒度": "按月", "是否可累加": "否",
        },
    ],

    # ---- 语义层 ----
    "semantic_layer": [
        {
            "id": 1, "status": "已发布", "pending": False, "abnormal": False,
            "语义名称": "用户行为语义模型", "物理表": "dwd_user_behavior_log",
            "字段映射": "user_id:userId, event_name:event, event_time:ts, device_id:did",
            "关联关系": "LEFT JOIN dim_user ON user_id", "过滤条件": "event_date >= CURRENT_DATE - 90",
            "安全规则": "用户身份字段脱敏", "描述说明": "将行为日志映射为统一的用户事件模型",
        },
        {
            "id": 2, "status": "已发布", "pending": False, "abnormal": False,
            "语义名称": "交易事实语义模型", "物理表": "dwd_trade_fact",
            "字段映射": "order_id:订单ID, user_id:userId, amount:实付金额, status:订单状态",
            "关联关系": "LEFT JOIN dim_product ON sku_id", "过滤条件": "order_status = 'completed'",
            "安全规则": "金额字段需要数据范围授权", "描述说明": "交易事实表的业务语义层映射",
        },
        {
            "id": 3, "status": "已验证", "pending": True, "abnormal": False,
            "语义名称": "用户画像语义模型", "物理表": "dim_user_profile",
            "字段映射": "user_id:userId, age:年龄, city:城市, level:会员等级",
            "关联关系": "", "过滤条件": "",
            "安全规则": "年龄、城市等敏感字段需授权", "描述说明": "用户基础画像维度表语义",
        },
        {
            "id": 4, "status": "已发布", "pending": False, "abnormal": False,
            "语义名称": "DAU指标语义", "物理表": "dwd_user_behavior_log",
            "字段映射": "user_id:userId, event_date=当日访问行为",
            "关联关系": "", "过滤条件": "event_date = :target_date",
            "安全规则": "按部门限定日期范围", "描述说明": "将DAU指标映射到行为日志表",
        },
    ],

    # ---- 多维立方 ----
    "cube_builder": [
        {
            "id": 1, "status": "已上线", "pending": False, "abnormal": False,
            "立方名称": "用户行为分析立方", "事实表": "dwd_user_behavior_log",
            "维度列表": "日期, 事件类型, 城市, 会员等级, 设备类型",
            "预聚合度量": "DAU:DISTINCT_COUNT, 事件数:COUNT, 人均事件:AVG",
            "分区策略": "按日期分区,日级", "刷新频率": "每日02:00",
            "存储引擎": "ClickHouse",
        },
        {
            "id": 2, "status": "已上线", "pending": False, "abnormal": False,
            "立方名称": "交易分析立方", "事实表": "dwd_trade_fact",
            "维度列表": "日期, 商品类目, 城市, 支付方式, 渠道来源",
            "预聚合度量": "GMV:SUM, 订单数:COUNT, 客单价:AVG",
            "分区策略": "按日期分区,小时级", "刷新频率": "每小时",
            "存储引擎": "Doris",
        },
        {
            "id": 3, "status": "构建中", "pending": True, "abnormal": False,
            "立方名称": "用户增长漏斗立方", "事实表": "dwd_funnel_events",
            "维度列表": "日期, 漏斗步骤, 渠道, 新老用户",
            "预聚合度量": "到达数:COUNT, 转化率:AVG, 流失率:AVG",
            "分区策略": "按日期分区,日级", "刷新频率": "每日06:00",
            "存储引擎": "ClickHouse",
        },
        {
            "id": 4, "status": "已上线", "pending": False, "abnormal": False,
            "立方名称": "营收多维分析立方", "事实表": "dwd_revenue_fact",
            "维度列表": "日期, 业务线, 地区, 客户等级, 产品类型",
            "预聚合度量": "营收:SUM, 成本:SUM, 毛利率:AVG",
            "分区策略": "按月分区,日级刷新", "刷新频率": "每日08:00",
            "存储引擎": "Doris",
        },
    ],

    # ---- 切片查询 ----
    "slice_query": [
        {
            "id": 1, "status": "已发布", "pending": False, "abnormal": False,
            "模板名称": "分城市日活趋势", "数据立方": "用户行为分析立方",
            "查询维值": "城市=北京;城市=上海;事件类型=页面访问",
            "过滤条件": "事件数>100", "排序规则": "DAU:DESC",
            "返回行数": "50", "缓存TTL": "300",
        },
        {
            "id": 2, "status": "已发布", "pending": False, "abnormal": False,
            "模板名称": "类目交易周报", "数据立方": "交易分析立方",
            "查询维值": "日期=本周", "过滤条件": "GMV>=10000",
            "排序规则": "GMV:DESC", "返回行数": "100", "缓存TTL": "600",
        },
        {
            "id": 3, "status": "已保存", "pending": True, "abnormal": False,
            "模板名称": "渠道转化对比", "数据立方": "用户增长漏斗立方",
            "查询维值": "渠道=信息流;渠道=搜索;漏斗步骤=注册",
            "过滤条件": "到达数>=50", "排序规则": "转化率:DESC",
            "返回行数": "20", "缓存TTL": "300",
        },
        {
            "id": 4, "status": "已发布", "pending": False, "abnormal": False,
            "模板名称": "新老用户行为差异", "数据立方": "用户行为分析立方",
            "查询维值": "新老用户=新用户;新老用户=老用户",
            "过滤条件": "", "排序规则": "事件数:DESC",
            "返回行数": "200", "缓存TTL": "1800",
        },
    ],

    # ---- 分群圈选 ----
    "segment_rule": [
        {
            "id": 1, "status": "已生效", "pending": False, "abnormal": False,
            "分群名称": "高价值流失风险用户", "人群类型": "行为属性组合",
            "筛选条件": "会员等级:gte:3;最近登录日期:lt:2026-10-01",
            "排除条件": "是否已投诉:eq:是", "交集策略": "all",
            "刷新周期": "每周一", "分群规模": "45200",
        },
        {
            "id": 2, "status": "已生效", "pending": False, "abnormal": False,
            "分群名称": "沉默唤醒目标用户", "人群类型": "生命周期筛选",
            "筛选条件": "最近访问日:lt:2026-09-15;注册日:gte:2026-01-01",
            "排除条件": "已注销:eq:是", "交集策略": "all",
            "刷新周期": "每两周", "分群规模": "128500",
        },
        {
            "id": 3, "status": "计算中", "pending": True, "abnormal": False,
            "分群名称": "高频交易核心用户", "人群类型": "RFM分层",
            "筛选条件": "月交易次数:gte:10;月交易金额:gte:5000;城市:in:北京,上海,深圳,杭州",
            "排除条件": "涉及风控:eq:是", "交集策略": "all",
            "刷新周期": "每日", "分群规模": "0",
        },
        {
            "id": 4, "status": "草稿", "pending": True, "abnormal": False,
            "分群名称": "新注册活跃用户", "人群类型": "行为事件筛选",
            "筛选条件": "注册日:gte:2026-10-01;首日事件数:gte:5",
            "排除条件": "", "交集策略": "all",
            "刷新周期": "每日", "分群规模": "0",
        },
    ],

    # ---- 看板布局 ----
    "dashboard_layout": [
        {
            "id": 1, "status": "已发布", "pending": False, "abnormal": False,
            "看板名称": "核心指标监控大盘", "所属业务域": "用户增长",
            "图表布局": "line:日活趋势:2:1:0:0;number:GMV:1:1:2:0;bar:城市分布:2:2:0:1;table:Top事件:2:2:2:1",
            "数据刷新间隔": "5分钟", "是否公开": "是",
            "创建人": "张三", "上次修改": "2026-10-15",
        },
        {
            "id": 2, "status": "已发布", "pending": False, "abnormal": False,
            "看板名称": "营收分析看板", "所属业务域": "营收分析",
            "图表布局": "number:总GMV:1:1:0:0;line:GMV趋势:2:1:1:0;bar:类目GMV:2:2:0:1;pie:支付方式占比:1:2:2:1",
            "数据刷新间隔": "10分钟", "是否公开": "否",
            "创建人": "李四", "上次修改": "2026-10-18",
        },
        {
            "id": 3, "status": "已发布", "pending": False, "abnormal": False,
            "看板名称": "用户留存分析看板", "所属业务域": "用户增长",
            "图表布局": "cohort:同期群矩阵:3:2:0:0;line:日留存趋势:2:1:0:2;number:7日留存率:1:1:3:0",
            "数据刷新间隔": "1小时", "是否公开": "是",
            "创建人": "王五", "上次修改": "2026-10-20",
        },
    ],

    # ---- 即席导出 ----
    "adhoc_export": [
        {
            "id": 1, "status": "已完成", "pending": False, "abnormal": False,
            "任务名称": "Q3分城市DAU明细", "查询SQL": "SELECT city, date, dau FROM cube_user_behavior WHERE q='2026Q3'",
            "导出格式": "csv", "行数限制": "50000", "是否压缩": "是",
            "分区过滤": "q='2026Q3'", "创建时间": "2026-10-20",
        },
        {
            "id": 2, "status": "执行中", "pending": True, "abnormal": False,
            "任务名称": "10月交易类目汇总", "查询SQL": "SELECT category, SUM(gmv) FROM cube_trade WHERE month='202610' GROUP BY category",
            "导出格式": "csv", "行数限制": "100000", "是否压缩": "否",
            "分区过滤": "month='202610'", "创建时间": "2026-10-22",
        },
        {
            "id": 3, "status": "排队中", "pending": True, "abnormal": False,
            "任务名称": "用户画像全量导出", "查询SQL": "SELECT * FROM dim_user_profile WHERE status='active'",
            "导出格式": "json", "行数限制": "2000000", "是否压缩": "是",
            "分区过滤": "", "创建时间": "2026-10-22",
        },
    ],

    # ---- 报表订阅 ----
    "report_subscription": [
        {
            "id": 1, "status": "已启用", "pending": False, "abnormal": False,
            "订阅名称": "核心指标日报", "报表对象": "核心指标监控大盘",
            "推送周期": "每日09:00", "推送渠道": "邮件",
            "接收人": "zhangsan@example.com,lisi@example.com", "推送格式": "PDF",
            "最近推送时间": "2026-10-22",
        },
        {
            "id": 2, "status": "已启用", "pending": False, "abnormal": False,
            "订阅名称": "周度营收简报", "报表对象": "营收分析看板",
            "推送周期": "每周一10:00", "推送渠道": "企业微信",
            "接收人": "wangwu@example.com,manager@example.com", "推送格式": "图片",
            "最近推送时间": "2026-10-21",
        },
        {
            "id": 3, "status": "已暂停", "pending": True, "abnormal": False,
            "订阅名称": "留存周报推送", "报表对象": "用户留存分析看板",
            "推送周期": "每周五16:00", "推送渠道": "消息推送",
            "接收人": "analyst@example.com", "推送格式": "Excel",
            "最近推送时间": "2026-10-14",
        },
    ],

    # ---- 异常检测 ----
    "anomaly_detect": [
        {
            "id": 1, "status": "监控中", "pending": False, "abnormal": False,
            "规则名称": "DAU暴跌检测", "监控指标": "DAU",
            "检测算法": "zscore", "阈值设置": "3.0",
            "参考周期": "7", "告警级别": "P1-严重",
            "是否启用": "是",
        },
        {
            "id": 2, "status": "监控中", "pending": False, "abnormal": False,
            "规则名称": "GMV异常波动检测", "监控指标": "GMV",
            "检测算法": "moving_avg", "阈值设置": "0.3",
            "参考周期": "14", "告警级别": "P2-警告",
            "是否启用": "是",
        },
        {
            "id": 3, "status": "已触发", "pending": False, "abnormal": True,
            "规则名称": "转化率骤降检测", "监控指标": "CONV_RATE",
            "检测算法": "iqr", "阈值设置": "2.0",
            "参考周期": "7", "告警级别": "P1-严重",
            "是否启用": "是",
        },
        {
            "id": 4, "status": "草稿", "pending": True, "abnormal": False,
            "规则名称": "订单量异常监控", "监控指标": "订单数",
            "检测算法": "zscore", "阈值设置": "2.5",
            "参考周期": "30", "告警级别": "P2-警告",
            "是否启用": "否",
        },
    ],

    # ---- 下钻路径 ----
    "drill_path": [
        {
            "id": 1, "status": "已启用", "pending": False, "abnormal": False,
            "路径名称": "GMV地区下钻", "起始维度": "全国",
            "下钻层级": "大区, 省份, 城市, 门店",
            "各层度量": "GMV, 订单数, 客单价",
            "是否启用手动": "是", "关联看板": "营收分析看板",
            "路径说明": "从全国总GMV逐层下钻到门店级明细",
        },
        {
            "id": 2, "status": "已启用", "pending": False, "abnormal": False,
            "路径名称": "用户行为漏斗下钻", "起始维度": "总用户",
            "下钻层级": "新老, 渠道, 城市, 设备",
            "各层度量": "DAU, 事件数, 人均事件",
            "是否启用手动": "是", "关联看板": "核心指标监控大盘",
            "路径说明": "从总体DAU逐层下钻至设备类型用户行为分析",
        },
        {
            "id": 3, "status": "草稿", "pending": True, "abnormal": False,
            "路径名称": "商品类目下钻", "起始维度": "全品类",
            "下钻层级": "一级类目, 二级类目, 三级类目, SKU",
            "各层度量": "GMV, 订单数, 回访转化率",
            "是否启用手动": "否", "关联看板": "营收分析看板",
            "路径说明": "从全品类总交易额逐层下钻到SKU级",
        },
    ],

    # ---- 数据血缘 ----
    "data_lineage": [
        {
            "id": 1, "status": "在线", "pending": False, "abnormal": False,
            "节点名称": "ods_user_behavior_raw", "节点类型": "table",
            "上游列表": "", "下游列表": "2,3",
            "数据量级": "500GB/月", "更新频率": "实时", "负责人": "数据平台组",
        },
        {
            "id": 2, "status": "在线", "pending": False, "abnormal": False,
            "节点名称": "dwd_user_behavior_log", "节点类型": "table",
            "上游列表": "1", "下游列表": "4,5",
            "数据量级": "200GB/月", "更新频率": "每小时", "负责人": "数据平台组",
        },
        {
            "id": 3, "status": "在线", "pending": False, "abnormal": False,
            "节点名称": "dwd_trade_fact", "节点类型": "table",
            "上游列表": "1", "下游列表": "6",
            "数据量级": "100GB/月", "更新频率": "每小时", "负责人": "数据平台组",
        },
        {
            "id": 4, "status": "在线", "pending": False, "abnormal": False,
            "节点名称": "cube_user_behavior", "节点类型": "metric",
            "上游列表": "2", "下游列表": "7,8",
            "数据量级": "50GB/月", "更新频率": "每日", "负责人": "分析平台组",
        },
        {
            "id": 5, "status": "在线", "pending": False, "abnormal": False,
            "节点名称": "DAU日报表", "节点类型": "report",
            "上游列表": "4", "下游列表": "9",
            "数据量级": "10MB/月", "更新频率": "每日", "负责人": "分析师A",
        },
        {
            "id": 6, "status": "在线", "pending": False, "abnormal": False,
            "节点名称": "cube_trade", "节点类型": "metric",
            "上游列表": "3", "下游列表": "7",
            "数据量级": "30GB/月", "更新频率": "每小时", "负责人": "分析平台组",
        },
        {
            "id": 7, "status": "在线", "pending": False, "abnormal": False,
            "节点名称": "核心指标监控大盘", "节点类型": "report",
            "上游列表": "4,6", "下游列表": "9",
            "数据量级": "5MB/月", "更新频率": "5分钟", "负责人": "分析师B",
        },
        {
            "id": 8, "status": "在线", "pending": False, "abnormal": False,
            "节点名称": "DAU指标定义", "节点类型": "column",
            "上游列表": "2", "下游列表": "5",
            "数据量级": "N/A", "更新频率": "N/A", "负责人": "数据治理组",
        },
        {
            "id": 9, "status": "在线", "pending": False, "abnormal": False,
            "节点名称": "高管看板", "节点类型": "report",
            "上游列表": "5,7", "下游列表": "",
            "数据量级": "1MB/月", "更新频率": "实时", "负责人": "管理组",
        },
        # ---- 门店/渠道两支加工链路（依赖复算演示，节点99故意不登记，模拟缺失上游） ----
        {
            "id": 10, "status": "在线", "pending": False, "abnormal": False,
            "节点名称": "ods_store_trade_daily", "节点类型": "table",
            "上游列表": "", "下游列表": "11",
            "数据量级": "20GB/月", "更新频率": "每日", "负责人": "数据平台组",
        },
        {
            "id": 11, "status": "在线", "pending": False, "abnormal": False,
            "节点名称": "dwd_store_clean", "节点类型": "table",
            "上游列表": "10", "下游列表": "12",
            "数据量级": "12GB/月", "更新频率": "每日", "负责人": "数据平台组",
        },
        {
            "id": 12, "status": "在线", "pending": False, "abnormal": False,
            "节点名称": "ads_store_daily_summary", "节点类型": "table",
            "上游列表": "11", "下游列表": "",
            "数据量级": "2GB/月", "更新频率": "每日", "负责人": "分析平台组",
        },
        {
            "id": 13, "status": "在线", "pending": False, "abnormal": False,
            "节点名称": "ods_channel_exposure_daily", "节点类型": "table",
            "上游列表": "", "下游列表": "14",
            "数据量级": "30GB/月", "更新频率": "每日", "负责人": "数据平台组",
        },
        {
            "id": 14, "status": "在线", "pending": False, "abnormal": False,
            "节点名称": "dwd_channel_order_clean", "节点类型": "table",
            "上游列表": "13,99", "下游列表": "15",
            "数据量级": "15GB/月", "更新频率": "每日", "负责人": "数据平台组",
        },
        {
            "id": 15, "status": "在线", "pending": False, "abnormal": False,
            "节点名称": "ads_channel_daily_summary", "节点类型": "table",
            "上游列表": "14", "下游列表": "",
            "数据量级": "3GB/月", "更新频率": "每日", "负责人": "分析平台组",
        },
    ],

    # ---- 查询调度 ----
    "query_scheduler": [
        {
            "id": 1, "status": "已完成", "pending": False, "abnormal": False,
            "计划名称": "每日行为数据ETL", "查询语句": "INSERT INTO dwd_user_behavior_log SELECT ... FROM ods_user_behavior_raw WHERE dt='CURRENT_DATE'",
            "执行周期": "每日02:00", "依赖任务": "",
            "超时分钟": "120", "失败重试": "3", "优先级": "高",
        },
        {
            "id": 2, "status": "执行中", "pending": True, "abnormal": False,
            "计划名称": "交易立方刷新", "查询语句": "REFRESH MATERIALIZED VIEW cube_trade",
            "执行周期": "每小时", "依赖任务": "每日行为数据ETL",
            "超时分钟": "30", "失败重试": "2", "优先级": "高",
        },
        {
            "id": 3, "status": "待调度", "pending": True, "abnormal": False,
            "计划名称": "用户画像更新", "查询语句": "UPDATE dim_user_profile SET ...",
            "执行周期": "每日06:00", "依赖任务": "每日行为数据ETL",
            "超时分钟": "60", "失败重试": "1", "优先级": "中",
        },
        {
            "id": 4, "status": "调度失败", "pending": True, "abnormal": True,
            "计划名称": "周报汇总计算", "查询语句": "SELECT ... 复杂聚合",
            "执行周期": "每周一08:00", "依赖任务": "交易立方刷新,用户画像更新",
            "超时分钟": "90", "失败重试": "2", "优先级": "中",
        },
        # ---- 门店链路：清洗 -> 日汇总，复算时前置输入已齐，可按拓扑次序执行 ----
        {
            "id": 5, "status": "待调度", "pending": True, "abnormal": False,
            "计划名称": "门店销售清洗",
            "查询语句": "INSERT INTO dwd_store_clean SELECT ... FROM ods_store_trade_daily WHERE dt='2026-11-21'",
            "执行周期": "每日03:00", "依赖任务": "",
            "超时分钟": "60", "失败重试": "3", "优先级": "高",
        },
        {
            "id": 6, "status": "待调度", "pending": True, "abnormal": False,
            "计划名称": "门店日汇总",
            "查询语句": "INSERT INTO ads_store_daily_summary SELECT ... FROM dwd_store_clean WHERE dt='2026-11-21'",
            "执行周期": "每日04:00", "依赖任务": "门店销售清洗",
            "超时分钟": "45", "失败重试": "3", "优先级": "高",
        },
        # ---- 渠道链路：上游节点99未登记，渠道清洗被实际阻塞，汇总随之阻塞 ----
        {
            "id": 7, "status": "待调度", "pending": True, "abnormal": False,
            "计划名称": "渠道订单清洗",
            "查询语句": "INSERT INTO dwd_channel_order_clean SELECT ... FROM ods_channel_exposure_daily, ads_channel_attribution WHERE dt='2026-11-21'",
            "执行周期": "每日03:30", "依赖任务": "",
            "超时分钟": "60", "失败重试": "3", "优先级": "高",
        },
        {
            "id": 8, "status": "待调度", "pending": True, "abnormal": False,
            "计划名称": "渠道日汇总",
            "查询语句": "INSERT INTO ads_channel_daily_summary SELECT ... FROM dwd_channel_order_clean WHERE dt='2026-11-21'",
            "执行周期": "每日04:30", "依赖任务": "渠道订单清洗",
            "超时分钟": "45", "失败重试": "3", "优先级": "高",
        },
        # ---- 循环依赖样本：两计划互指，均禁止执行 ----
        {
            "id": 9, "status": "待调度", "pending": True, "abnormal": False,
            "计划名称": "循环任务甲", "查询语句": "SELECT 1",
            "执行周期": "每日05:00", "依赖任务": "循环任务乙",
            "超时分钟": "30", "失败重试": "1", "优先级": "低",
        },
        {
            "id": 10, "status": "待调度", "pending": True, "abnormal": False,
            "计划名称": "循环任务乙", "查询语句": "SELECT 2",
            "执行周期": "每日05:00", "依赖任务": "循环任务甲",
            "超时分钟": "30", "失败重试": "1", "优先级": "低",
        },
        # ---- 未登记计划依赖样本：前置计划不存在，不得进入执行 ----
        {
            "id": 11, "status": "待调度", "pending": True, "abnormal": False,
            "计划名称": "孤儿汇总任务", "查询语句": "SELECT 3",
            "执行周期": "每日07:00", "依赖任务": "不存在的前置任务",
            "超时分钟": "30", "失败重试": "1", "优先级": "中",
        },
    ],

    # ---- 结果缓存 ----
    "result_cache": [
        {
            "id": 1, "status": "有效", "pending": False, "abnormal": False,
            "缓存键": "cache_dau_city_20261022", "查询描述": "分城市DAU查询",
            "结果行数": "100", "字节大小": "4096",
            "创建时间": "2026-10-22 08:00", "TTL秒": "300", "命中次数": "152",
        },
        {
            "id": 2, "status": "有效", "pending": False, "abnormal": False,
            "缓存键": "cache_gmv_category_w42", "查询描述": "类目交易汇总查询",
            "结果行数": "50", "字节大小": "1024",
            "创建时间": "2026-10-21 10:00", "TTL秒": "600", "命中次数": "89",
        },
        {
            "id": 3, "status": "已失效", "pending": True, "abnormal": False,
            "缓存键": "cache_user_retain_w41", "查询描述": "用户留存率查询",
            "结果行数": "200", "字节大小": "8192",
            "创建时间": "2026-10-15 12:00", "TTL秒": "86400", "命中次数": "234",
        },
    ],

    # ---- 数据范围 ----
    "olap_scope": [
        {
            "id": 1, "status": "已生效", "pending": False, "abnormal": False,
            "规则名称": "华东分析师范围", "数据范围": "cube_user_behavior,cube_trade",
            "授权对象": "分析师A,分析师B", "可见字段": "城市,事件类型,GMV,订单数,日期,会员等级",
            "行过滤条件": "城市 in ('上海','杭州','南京','苏州')",
            "生效时间": "2026-09-01", "失效时间": "2026-12-31",
        },
        {
            "id": 2, "status": "已生效", "pending": False, "abnormal": False,
            "规则名称": "管理者全量范围", "数据范围": "cube_user_behavior,cube_trade,cube_funnel",
            "授权对象": "管理组", "可见字段": "全部",
            "行过滤条件": "",
            "生效时间": "2026-01-01", "失效时间": "2026-12-31",
        },
        {
            "id": 3, "status": "已冻结", "pending": False, "abnormal": True,
            "规则名称": "实习生受限范围", "数据范围": "cube_user_behavior",
            "授权对象": "实习生C", "可见字段": "日期,事件类型,城市",
            "行过滤条件": "日期 >= '2026-06-01' and 日期 <= '2026-09-01'",
            "生效时间": "2026-06-01", "失效时间": "2026-09-01",
        },
    ],

    # ---- 归因模型 ----
    "attribution_model": [
        {
            "id": 1, "status": "已生效", "pending": False, "abnormal": False,
            "模型名称": "首触归因模型", "归因对象": "用户注册转化",
            "归因窗口": "30天", "触点权重": "首次100%",
            "衰减方式": "无衰减", "首次归因": "1.0", "末次归因": "0.0",
        },
        {
            "id": 2, "status": "已生效", "pending": False, "abnormal": False,
            "模型名称": "时间衰减归因", "归因对象": "购买转化",
            "归因窗口": "7天", "触点权重": "按时间指数衰减",
            "衰减方式": "time_decay", "首次归因": "", "末次归因": "",
        },
        {
            "id": 3, "status": "计算中", "pending": True, "abnormal": False,
            "模型名称": "U型归因模型", "归因对象": "首充转化",
            "归因窗口": "14天", "触点权重": "首次40%+末次40%+中间20%",
            "衰减方式": "无衰减", "首次归因": "0.4", "末次归因": "0.4",
        },
    ],

    # ---- 同期群分析 ----
    "cohort_analysis": [
        {
            "id": 1, "status": "已完成", "pending": False, "abnormal": False,
            "群组名称": "Q3注册用户留存", "初始事件": "注册",
            "回访事件": "登录", "分析周期": "7",
            "群组大小": "120500", "保留计算": "standard",
            "显示格式": "百分比矩阵",
        },
        {
            "id": 2, "status": "已完成", "pending": False, "abnormal": False,
            "群组名称": "首充用户回访分析", "初始事件": "首次充值",
            "回访事件": "二次充值", "分析周期": "7",
            "群组大小": "45000", "保留计算": "bounded",
            "显示格式": "热力图",
        },
        {
            "id": 3, "status": "分析中", "pending": True, "abnormal": False,
            "群组名称": "新活动参与用户留存", "初始事件": "参与活动A",
            "回访事件": "访问App", "分析周期": "7",
            "群组大小": "78900", "保留计算": "standard",
            "显示格式": "线图+百分比",
        },
    ],

    # ---- 查询加速 ----
    "query_accelerator": [
        {
            "id": 1, "status": "已启用", "pending": False, "abnormal": False,
            "配置名称": "DAU查询物化加速", "目标查询": "分城市DAU查询",
            "加速方式": "物化视图", "预计算范围": "最近90天, 前100城市",
            "刷新策略": "每小时刷新", "命中率目标": "95%", "存储预算": "10GB",
        },
        {
            "id": 2, "status": "预热中", "pending": True, "abnormal": False,
            "配置名称": "GMV汇总结果缓存", "目标查询": "类目GMV汇总",
            "加速方式": "结果缓存", "预计算范围": "所有类目, 最近30天",
            "刷新策略": "每30分钟刷新", "命中率目标": "90%", "存储预算": "2GB",
        },
        {
            "id": 3, "status": "草稿", "pending": True, "abnormal": False,
            "配置名称": "用户画像预计算", "目标查询": "用户分群关联查询",
            "加速方式": "预计算", "预计算范围": "活跃用户全量",
            "刷新策略": "每日刷新", "命中率目标": "80%", "存储预算": "50GB",
        },
    ],

    # ---- 实验分析 ----
    "ab_analysis": [
        {
            "id": 1, "status": "已结束", "pending": False, "abnormal": False,
            "实验名称": "新注册流程AB测试", "对照组": "原注册流程",
            "实验组": "简化注册流程", "核心指标": "注册转化率",
            "置信度要求": "95%", "最小样本量": "10000", "实验周期": "14天",
        },
        {
            "id": 2, "status": "进行中", "pending": True, "abnormal": False,
            "实验名称": "推荐算法AB测试", "对照组": "协同过滤算法",
            "实验组": "深度学习算法", "核心指标": "点击率",
            "置信度要求": "95%", "最小样本量": "20000", "实验周期": "21天",
        },
        {
            "id": 3, "status": "草稿", "pending": True, "abnormal": False,
            "实验名称": "定价策略AB测试", "对照组": "统一定价",
            "实验组": "动态定价", "核心指标": "GMV",
            "置信度要求": "90%", "最小样本量": "5000", "实验周期": "30天",
        },
    ],
}