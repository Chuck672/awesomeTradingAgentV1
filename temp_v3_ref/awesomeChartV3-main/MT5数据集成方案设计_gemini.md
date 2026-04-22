你的这个修改方案非常具有前瞻性！**DuckDB + Parquet** 是目前华尔街量化机构在本地处理海量时序数据的“黄金标准”（远超传统关系型数据库）。而 **ZeroMQ + 轮询回退** 的双通道设计，则展现了极高的工程成熟度。

如果将未来的 **AI Trading Bot（AI 自动交易机器人）** 纳入考量，系统的要求将从单一的“可视化”升级为 **“高并发、低延迟、可复用、数据绝对一致”**。

基于你目前的优秀构想，我为你补充一些针对 AI 场景的**关键优化建议**，并重新梳理整套架构设计。

---

### 一、 针对 AI Trading Bot 的核心架构建议

1.  **ZMQ 模式升级：从 PUSH/PULL 改为 PUB/SUB（发布/订阅）**
    *   **为什么？** PUSH/PULL 是一对一的，消费后数据就没了。当你引入 AI Bot 后，你的系统将有三个消费者：1. 前端图表 (WebSocket 推送)；2. 实时数据落盘服务 (存入数据库)；3. **AI Bot (实时接收 K 线/Tick 进行推理预测)**。
    *   **方案：** MT5 的 EA 作为 Publisher (PUB)，Python 后端作为 Subscriber (SUB)。这样你的架构完全解耦，未来再加几个 AI 模型也不会相互影响。
2.  **“冷热数据分离” (Hot/Cold Storage)**
你的想法非常务实且极具工程价值！**拒绝纯内存缓存，改用持久化的 DuckDB 文件作为“热存储”，按月切分 Parquet 作为“冷存储”**，这是一个极其健壮的设计。

纯内存缓存最大的痛点确实如你所说：一旦重启服务，丢失当前进度，必须重新向 MT5 发起大批量的数据请求，这既浪费时间，又容易触发 MT5 API 的限流或卡顿。

基于你的思路，我完全赞同，并为你梳理出以下**优化后的 MT5 数据集成与存储流转方案**。

---

### 一、 核心存储架构定义 (Hot / Cold 持久化分离)

我们引入一个本地磁盘上的 DuckDB 文件（例如 `hot_data.duckdb`）来替代内存。

1.  **热数据层 (Hot Tier): `hot_data.duckdb` (磁盘文件)**
    *   **职责**：存储**当前未归档月份**（例如现在是 5 月，这里就存 5 月的全部数据）以及**实时追加**的数据。
    *   **优势**：进程关闭数据不丢失；重启毫秒级加载；支持 SQL 强校验（利用 UNIQUE 约束防止重复数据）。
2.  **冷数据层 (Cold Tier): `{symbol}_{year}_{month}.parquet`**
    *   **职责**：存储**历史完整月份**的数据。
    *   **优势**：极致的读取速度和压缩比，文件不可变，方便跨设备迁移或直接丢给 AI 训练脚本。
3.  **元数据层 (SQLite): `meta.db`**
    *   **职责**：记录系统状态（如：各 Symbol 最后一次同步的时间戳，哪些月份已经成功生成了 Parquet）。

---

### 二、 核心流转逻辑重写 (Startup & Sync)

当你的 APP（或后端服务）启动，或者用户在前端切换/打开某个 Symbol 时，系统将执行一个被称为 **“对齐与归档 (Reconciliation & Rollover)”** 的标准流程。

假设今天是 **5 月 15 日**，用户打开了 `EURUSD`。

#### 第一步：状态检查与自动归档 (Parquet Rollover)
1.  Python 连接 `hot_data.duckdb`，查询 `EURUSD` 表中最老和最新的时间戳。
2.  发现 `hot_data.duckdb` 中竟然还留有 **4月份** 的数据。
3.  **触发归档**：
    *   将 DuckDB 中的 4月数据导出：`COPY (SELECT * FROM EURUSD WHERE month=4) TO 'data/EURUSD_2024_04.parquet' (FORMAT PARQUET);`
    *   从 DuckDB 中删除 4月数据：`DELETE FROM EURUSD WHERE month=4;`
    *   *注：这一步极快，DuckDB 原生支持一键导出 Parquet。*

#### 第二步：断点续传 (MT5 Catch-up)
1.  查询 `hot_data.duckdb` 中 `EURUSD` 的最后一条记录的时间戳（例如：`2024-05-14 22:00:00`，说明昨晚关机了）。
2.  调用 MT5 API，**仅拉取** `2024-05-14 22:00:00` 到 **现在 (5月15日)** 的缺失数据。
3.  将这批增量数据批量写入 `hot_data.duckdb`。
4.  此时，本地数据已完全与 MT5 同步。

#### 第三步：响应前端图表 (Data Serving)
1.  前端请求历史数据。
2.  Python 构建一条混合查询：
    ```sql
    -- DuckDB 可以直接在一个 SQL 里联合查询 Parquet 和自己的本地表
    SELECT * FROM read_parquet('data/EURUSD/*.parquet')
    UNION ALL
    SELECT * FROM EURUSD  -- 查 hot_data.duckdb
    ORDER BY time ASC;
    ```
3.  瞬间返回给 Lightweight Charts 进行渲染。

#### 第四步：实时数据接入 (Real-time Appending)
1.  ZMQ 接收到 MT5 推送的最新 K 线/Tick。
2.  Python 将消息通过 WebSocket 推给前端，同时推送给 AI Bot。
3.  **写入热库**：将单条数据 `INSERT` 进 `hot_data.duckdb`。
    *   *(技术细节：DuckDB 虽然是列式数据库，不太擅长高频单行插入，但如果你使用的是 M1 级别的 K 线，每分钟 1 次插入对 DuckDB 来说毫无压力。如果你要存秒级 Tick 级别，可以在 Python 端用一个容量为 100 的 List 做微批次批量插入)*。

---

### 三、 架构设计图示

```text
[MT5 Terminal]
      │
      ├─ (历史追溯 API) ──────┐
      │                       ▼
      ├─ (实时 ZMQ PUB) ──► [ Python 核心引擎 (FastAPI + 调度器) ]
                              │           │              │
    ┌─────────────────────────┘           │              └──────────────┐
    ▼                                     ▼                             ▼
[ 1. 断点续传 & 归档 ]             [ 2. 实时分发 ]                [ 3. 查询聚合引擎 ]
    │                                     │                             │
    │ (写入 & 清理)                  (WS & ZMQ SUB)                    (SQL 联合查询)
    ▼                                     ▼                             ▼
【热存储】hot_data.duckdb           [ Lightweight UI ]              (冷热数据拼接)
    │                               [ AI Trading Bot ]                  ▲
    │ (按月自动 Dump)                                                   │
    ▼                                                                   │
【冷存储】Parquet 文件夹 ──────────────────────────────────────────────────┘
```

---

### 四、 代码实现的关键建议 (DuckDB 的正确姿势)

在你的设想下，如何优雅地使用 DuckDB 是成败的关键：

**1. 利用 `ON CONFLICT` 防止重复写入**
在拉取 MT5 数据补齐断点时，最容易发生边缘时间的重叠写入。DuckDB 支持类似 SQLite 的主键冲突处理：
```sql
CREATE TABLE IF NOT EXISTS EURUSD (
    time TIMESTAMP PRIMARY KEY,
    open DOUBLE,
    high DOUBLE,
    low DOUBLE,
    close DOUBLE,
    tick_volume BIGINT,
    source VARCHAR
);

-- 插入新数据，如果时间戳存在，则更新（覆盖）
INSERT INTO EURUSD (time, open, high, low, close, tick_volume, source)
VALUES (?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (time) DO UPDATE 
SET open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low, close=EXCLUDED.close;
```

**2. 归档逻辑的异步化**
检查月份和导出 Parquet 的操作虽然快，但不应该阻塞用户打开图表的请求。
建议：用户打开图表 -> 触发 MT5 增量补齐 -> 返回冷热聚合数据给前端渲染。 **同时，派生一个异步后台任务（Background Task）** 去检查并执行跨月归档。

**3. 轻量化 API 数据传输**
考虑到未来 AI Bot 需要海量数据训练，而 Lightweight Charts 只需要画图。
当前端请求数据时，可以通过参数限制：`GET /history?symbol=EURUSD&points=5000`。DuckDB 在执行上述 `UNION ALL` 的 SQL 时，可以直接在末尾加上 `LIMIT 5000`，让数据库引擎去做截断，避免 Python 加载多余数据撑爆内存。

### 总结

你提出的 **“本地持久化 DuckDB + 历史 Parquet + 月度 Rollover”** 方案非常完美。它彻底解决了“应用重启导致数据断层和重新拉取”的痛点。

这个架构不仅对于图表展示是零延迟的（热启动），而且对于 AI Bot 来说，随时可以从磁盘读取绝对连续、没有缺失、自带数据源标记 (`source: zmq` 或 `poll`) 的高质量数据集。这就是一套准企业级的量化数据底座。

3.  **特征工程 (Feature Engineering) 管道的预留**
    *   AI 模型需要的Chart Scene， 不仅仅是 OHLCV，还需要技术指标、时间特征,  趋势与结构 (Trend), 关键水平，动能情绪等。在请求历史数据或实时数据流经系统时，需要预留一个统一的**“特征计算层”**，确保前端图表看到的指标和 AI 吃到的一致。

---

### 二、 全新整理的设计方案 (AI 量化图表级架构)

整个系统分为四大层：**数据源层 -> 核心引擎层 (Python) -> 存储层 -> 应用层**。

#### 1. 数据源层 (MT5 端)
*   **MQL5 EA (Expert Advisor):**
    *   监听 `OnCalculate` (每根新 K 线) 或 `OnTick` (每次报价)。
    *   将数据打包成 JSON 字符串，包含字段：`{'symbol': 'EURUSD', 'tf': 'M1', 'time': 169000000, 'o': 1.1, 'h': 1.2, ..., 'source': 'zmq'}`。
    *   通过 ZMQ `PUB` Socket 广播出去。

#### 2. 存储层 (本地混合架构)
*   **配置中心 (SQLite):**
    *   存储 `symbols` 列表（哪些品种开启了交易/图表）。
    *   存储系统配置、AI 模型的元数据（如运行状态、持仓记录）。
*   **历史数据湖 (Parquet):**
    *   目录结构：`data/{symbol}/{timeframe}/{year}_{month}.parquet`
    *   绝对的冷数据，极高压缩比。
*   **查询引擎 (DuckDB):**
    *   不存储数据，只作为计算引擎。
    *   SQL 示例：`SELECT * FROM read_parquet('data/EURUSD/M1/*.parquet') WHERE time >= ?`

#### 3. 核心引擎层 (Python + FastAPI Backend)
这是系统的“大脑”，负责调度。建议使用 `asyncio`。

*   **模块 A: 数据订阅与分发 (The Router)**
    *   后台常驻协程，连接 ZMQ `SUB`，监听 MT5 广播。
    *   **异常回退逻辑：** 维护一个心跳时间戳，如果超过 N 秒没有收到 ZMQ 数据，自动触发 `MT5 Python API` 的 Poll 机制拉取缺失的 K 线，并将这些数据的 `source` 标记为 `poll`。
    *   拿到最新数据后，将数据推入一个内部的 `asyncio.Queue`，分发给不同组件。
*   **模块 B: 热数据管理器 (Hot Data Manager)**
    *   接收最新数据，缓存在内存的 Pandas DataFrame 中。
    *   负责在每天午夜将内存数据刷入（Flush）为对应的 Parquet 文件。
*   **模块 C: API 服务 (FastAPI)**
    *   **REST 接口 (`/history`)**：接收前端请求。Python 内部使用 DuckDB 查询 Parquet (冷) + 内存 DataFrame (热)，将两者拼接成完整的 DataFrame，转 JSON 返回给前端。
    *   **WebSocket 接口 (`/ws`)**：前端建立连接后，直接从内部的事件流中获取最新 K 线，推送给 Lightweight Charts。

#### 4. 应用层 (消费者)
*   **前端图表 (Lightweight Charts):**
    *   负责可视化。调用 REST 拉历史，连 WS 接实时跳动。
*   **AI Trading Bot (独立进程或协程):**
    *   同样订阅后端的实时数据流或直接连 ZMQ。
    *   利用历史数据 API 拉取批量数据进行批量推理（或模型训练）。
    *   将生成的交易信号通过 Python MT5 API 发送回 MT5 执行下单。

---

### 三、 核心代码结构示例

为了让你更直观地理解，这里展示**核心引擎层**整合 DuckDB 和双通道的伪代码/核心逻辑：

```python
import asyncio
import zmq
import zmq.asyncio
import duckdb
import pandas as pd
import MetaTrader5 as mt5
from fastapi import FastAPI, WebSocket

app = FastAPI()

# --- 1. 混合存储查询逻辑 (DuckDB + 热数据) ---
hot_data_cache = {} # 格式: {'EURUSD_M1': pd.DataFrame}

def get_combined_history(symbol: str, timeframe: str):
    # 1. 用 DuckDB 从 Parquet 加载冷数据
    # DuckDB 原生支持输出到 Pandas
    cold_df = duckdb.query(f"SELECT * FROM 'data/{symbol}/{timeframe}/*.parquet'").df()
    
    # 2. 获取热数据
    hot_df = hot_data_cache.get(f"{symbol}_{timeframe}", pd.DataFrame())
    
    # 3. 拼接并去重
    if not hot_df.empty:
        combined_df = pd.concat([cold_df, hot_df]).drop_duplicates(subset=['time'], keep='last')
    else:
        combined_df = cold_df
        
    return combined_df

# --- 2. ZMQ 实时接收与回退机制 ---
async def zmq_listener():
    context = zmq.asyncio.Context()
    socket = context.socket(zmq.SUB)
    socket.connect("tcp://127.0.0.1:5555")
    socket.setsockopt_string(zmq.SUBSCRIBE, "") # 订阅所有品种

    last_received_time = asyncio.get_event_loop().time()

    while True:
        try:
            # 加上 timeout 避免死等，以便检查回退机制
            msg = await asyncio.wait_for(socket.recv_json(), timeout=2.0)
            
            # 记录数据来源，更新热数据缓存...
            msg['source'] = 'zmq'
            update_hot_cache(msg)
            
            # 将消息广播给 WebSocket UI 和 AI Bot
            await broadcast_to_subscribers(msg)
            
            last_received_time = asyncio.get_event_loop().time()

        except asyncio.TimeoutError:
            # --- 回退机制 (Poll) ---
            print("ZMQ 超时，触发 MT5 Poll 回退...")
            # 伪代码：检查哪些品种需要拉取
            # missing_data = mt5.copy_rates_from_pos(...)
            # 标记 missing_data['source'] = 'poll'
            # update_hot_cache(missing_data)
            # broadcast_to_subscribers(missing_data)

@app.on_event("startup")
async def startup_event():
    mt5.initialize()
    # 启动后台监听任务
    asyncio.create_task(zmq_listener())
```

### 总结

你的修改非常到位。**DuckDB + SQLite + Parquet + ZMQ PUB/SUB** 的组合不仅满足你当前的“图表快速开发”，而且是一套可以直接过渡到“高频/中频量化交易系统”的标准底层架构。前端用 Lightweight Charts 渲染这套后端吐出的数据，体验将丝滑无比。