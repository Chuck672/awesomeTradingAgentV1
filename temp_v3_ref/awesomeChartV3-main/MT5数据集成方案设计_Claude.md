# 面向AI Trading Bot的完整系统设计方案

## 架构决策分析

在加入AI Trading Bot条件后，需要重新审视几个关键问题：

```
核心矛盾：
├── 历史数据需求：大批量、高压缩、列式查询（Parquet/DuckDB ✅）
├── 实时数据需求：低延迟、可靠、有序（ZMQ ✅）
├── AI训练需求：特征工程、时间对齐、无泄露分割
├── Bot执行需求：信号确定性、回测一致性、风险控制
└── 系统需求：解耦、可观测、可回放
```

### 方案修改意见

| 原方案 | 问题 | 修改建议 |
|--------|------|---------|
| DuckDB直接供前端 | AI训练时会锁库 | 读写分离，加连接池 |
| ZMQ直推前端 | Bot和前端抢消息 | 加消息总线，多消费者 |
| Parquet按年分割 | AI需要跨年特征 | 增加特征缓存层 |
| 无序列化格式规范 | Bot/前端数据不一致 | 统一Arrow格式 |
| 无回放机制 | Bot无法离线验证 | 加历史回放通道 |

---

## 完整项目结构

```
trading-platform/
├── data/
│   ├── market/                     # Parquet历史数据
│   │   ├── EURUSD/
│   │   │   ├── M1/
│   │   │   │   ├── 2022.parquet
│   │   │   │   └── 2023.parquet
│   │   │   └── H1/
│   │   │       └── 2023.parquet
│   │   └── XAUUSD/
│   ├── features/                   # 预计算特征缓存
│   │   └── EURUSD_H1_features.parquet
│   └── db/
│       ├── market.duckdb           # 实时查询层
│       └── config.db               # SQLite配置
│
├── backend/
│   ├── main.py
│   ├── config.py
│   │
│   ├── core/                       # 核心基础设施
│   │   ├── message_bus.py          # 消息总线（ZMQ发布）
│   │   ├── event_store.py          # 事件溯源存储
│   │   └── health.py               # 健康检查
│   │
│   ├── data_sources/
│   │   ├── base.py
│   │   ├── mt5_source.py           # MT5 ZMQ+Poll双通道
│   │   ├── yfinance_source.py
│   │   └── manager.py
│   │
│   ├── database/
│   │   ├── parquet_store.py        # Parquet读写管理
│   │   ├── duck_db.py              # DuckDB查询层
│   │   └── sqlite_db.py
│   │
│   ├── services/
│   │   ├── ingestion.py            # 数据摄入服务
│   │   ├── historical.py           # 历史数据服务
│   │   ├── realtime.py             # 实时数据服务
│   │   ├── feature.py              # 特征工程服务
│   │   └── replay.py               # 历史回放服务
│   │
│   └── api/
│       ├── routes/
│       └── websocket.py
│
├── ai_bot/                         # AI Bot模块（独立进程）
│   ├── bot_main.py                 # Bot入口
│   ├── data_client.py              # 数据消费客户端
│   ├── feature_pipeline.py         # 特征管道
│   ├── models/
│   │   ├── base_model.py
│   │   └── lstm_model.py
│   ├── strategy/
│   │   ├── signal_generator.py     # 信号生成
│   │   └── risk_manager.py         # 风险控制
│   └── backtest/
│       └── engine.py               # 回测引擎
│
└── frontend/
    └── src/
```

---

## 核心基础设施

### 消息总线

```python
# backend/core/message_bus.py
"""
消息总线 - 系统神经中枢
解决多消费者（前端、AI Bot、日志）抢消息问题
使用ZMQ PUB/SUB模式，支持主题过滤
"""
import zmq
import zmq.asyncio
import json
import time
import asyncio
from dataclasses import dataclass, asdict
from typing import Optional
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class Topic(str, Enum):
    """消息主题定义"""
    BAR_UPDATE   = "BAR"        # K线更新
    TICK         = "TICK"       # Tick数据
    BAR_CLOSED   = "CLOSED"     # K线关闭（已确认）
    SIGNAL       = "SIGNAL"     # AI交易信号
    EXECUTION    = "EXEC"       # 订单执行
    SYSTEM       = "SYS"        # 系统消息


@dataclass
class MarketMessage:
    """统一消息格式"""
    topic:      str
    symbol:     str
    timeframe:  str
    timestamp:  int             # Unix ms时间戳
    source:     str             # mt5 | yfinance | replay
    payload:    dict
    seq:        int = 0         # 序列号，用于检测丢包
    
    def to_frames(self) -> list:
        """序列化为ZMQ多帧消息"""
        topic_filter = f"{self.topic}.{self.symbol}.{self.timeframe}"
        body = json.dumps(asdict(self))
        return [
            topic_filter.encode(),
            body.encode()
        ]
    
    @classmethod
    def from_frames(cls, frames: list) -> 'MarketMessage':
        data = json.loads(frames[1])
        return cls(**data)


class MessageBus:
    """
    ZMQ PUB/SUB 消息总线
    
    拓扑结构:
    MT5Source ──→ [MessageBus PUB :5555] ──→ Frontend SUB
                                          ──→ AI Bot SUB  
                                          ──→ Logger SUB
    """
    
    PUB_PORT  = 5555    # 发布端口
    XPUB_PORT = 5556    # 扩展发布（可监控订阅者）
    
    def __init__(self):
        self.ctx = zmq.asyncio.Context()
        self._seq = 0
        self._pub_socket = None
        self._running = False
    
    async def start(self):
        self._pub_socket = self.ctx.socket(zmq.PUB)
        self._pub_socket.setsockopt(zmq.SNDHWM, 10000)  # 发送队列上限
        self._pub_socket.bind(f"tcp://*:{self.PUB_PORT}")
        self._running = True
        logger.info(f"MessageBus started on port {self.PUB_PORT}")
    
    async def publish(self, msg: MarketMessage):
        """发布消息到总线"""
        if not self._pub_socket:
            return
        
        self._seq += 1
        msg.seq = self._seq
        
        await self._pub_socket.send_multipart(msg.to_frames())
    
    async def publish_bar(
        self,
        symbol: str,
        timeframe: str,
        bar: dict,
        source: str,
        is_closed: bool = False
    ):
        """快捷方法：发布K线消息"""
        topic = Topic.BAR_CLOSED if is_closed else Topic.BAR_UPDATE
        msg = MarketMessage(
            topic=topic.value,
            symbol=symbol,
            timeframe=timeframe,
            timestamp=int(time.time() * 1000),
            source=source,
            payload={**bar, "is_closed": is_closed}
        )
        await self.publish(msg)
    
    def stop(self):
        self._running = False
        if self._pub_socket:
            self._pub_socket.close()
        self.ctx.term()


class MessageBusSubscriber:
    """
    消息总线订阅者基类
    AI Bot和前端网关都继承此类
    """
    
    def __init__(self, host: str = "localhost"):
        self.host = host
        self.ctx = zmq.asyncio.Context()
        self._sub_socket = None
        self._last_seq: dict = {}   # 检测丢包
    
    def connect(self, topics: list[str] = None):
        """连接并订阅主题"""
        self._sub_socket = self.ctx.socket(zmq.SUB)
        
        # 关键：设置接收缓冲
        self._sub_socket.setsockopt(zmq.RCVHWM, 10000)
        self._sub_socket.connect(
            f"tcp://{self.host}:{MessageBus.PUB_PORT}"
        )
        
        if topics:
            for topic in topics:
                self._sub_socket.setsockopt_string(zmq.SUBSCRIBE, topic)
        else:
            self._sub_socket.setsockopt_string(zmq.SUBSCRIBE, "")
    
    async def listen(self):
        """消息监听循环"""
        while True:
            try:
                frames = await self._sub_socket.recv_multipart()
                msg = MarketMessage.from_frames(frames)
                
                # 丢包检测
                key = f"{msg.symbol}_{msg.timeframe}"
                last = self._last_seq.get(key, 0)
                if msg.seq > last + 1:
                    logger.warning(
                        f"Packet loss detected: {key} "
                        f"expected {last+1}, got {msg.seq}"
                    )
                self._last_seq[key] = msg.seq
                
                await self.on_message(msg)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Subscriber error: {e}")
    
    async def on_message(self, msg: MarketMessage):
        """子类重写此方法处理消息"""
        raise NotImplementedError
    
    def disconnect(self):
        if self._sub_socket:
            self._sub_socket.close()
```

---

### 事件溯源存储

```python
# backend/core/event_store.py
"""
事件溯源存储
记录所有市场事件，支持任意时间点回放
这是AI Bot训练和回测的数据基础
"""
import sqlite3
import json
import time
from pathlib import Path
from typing import Iterator, Optional
from .message_bus import MarketMessage


class EventStore:
    """
    将所有消息总线事件持久化到SQLite
    设计原则：只增不改，保持完整事件历史
    """
    
    def __init__(self, db_path: str = "data/db/events.db"):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._init()
    
    def _init(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    seq         INTEGER NOT NULL,
                    topic       TEXT NOT NULL,
                    symbol      TEXT NOT NULL,
                    timeframe   TEXT NOT NULL,
                    timestamp   INTEGER NOT NULL,  -- Unix ms
                    source      TEXT NOT NULL,
                    payload     TEXT NOT NULL,     -- JSON
                    received_at INTEGER NOT NULL   -- 本地接收时间
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_query
                ON events(symbol, timeframe, timestamp)
            """)
    
    def append(self, msg: MarketMessage):
        """追加事件"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO events 
                (seq, topic, symbol, timeframe, timestamp, 
                 source, payload, received_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                msg.seq, msg.topic, msg.symbol, msg.timeframe,
                msg.timestamp, msg.source,
                json.dumps(msg.payload),
                int(time.time() * 1000)
            ])
    
    def replay(
        self,
        symbol: str,
        timeframe: str,
        start_ms: int,
        end_ms: int,
        speed: float = 1.0     # 回放速度倍率
    ) -> Iterator[MarketMessage]:
        """
        历史事件回放
        用于Bot离线验证和回测
        """
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("""
                SELECT seq, topic, symbol, timeframe, 
                       timestamp, source, payload
                FROM events
                WHERE symbol = ? AND timeframe = ?
                  AND timestamp BETWEEN ? AND ?
                ORDER BY timestamp ASC, seq ASC
            """, [symbol, timeframe, start_ms, end_ms]).fetchall()
        
        last_ts = None
        for row in rows:
            seq, topic, sym, tf, ts, src, payload = row
            
            # 模拟真实时间间隔
            if last_ts and speed > 0:
                delay = (ts - last_ts) / 1000 / speed
                time.sleep(min(delay, 1.0))  # 最多等1秒
            last_ts = ts
            
            yield MarketMessage(
                topic=topic,
                symbol=sym,
                timeframe=tf,
                timestamp=ts,
                source=f"replay:{src}",
                payload=json.loads(payload),
                seq=seq
            )
```

---

## 数据存储层

### Parquet分层存储

```python
# backend/database/parquet_store.py
"""
Parquet分层存储管理
目录结构: data/market/{SYMBOL}/{TIMEFRAME}/{YEAR}.parquet
"""
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pathlib import Path
from typing import Optional, List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Arrow Schema定义 - 确保AI Bot和前端数据类型一致
OHLCV_SCHEMA = pa.schema([
    pa.field('timestamp', pa.timestamp('ms', tz='UTC')),
    pa.field('open',      pa.float64()),
    pa.field('high',      pa.float64()),
    pa.field('low',       pa.float64()),
    pa.field('close',     pa.float64()),
    pa.field('volume',    pa.float64()),
    pa.field('source',    pa.string()),
])


class ParquetStore:
    """
    Parquet存储管理器
    
    写入策略：
    - 实时数据 → 先写DuckDB（热存储）
    - 每日凌晨 → 归档到Parquet（冷存储）
    - 跨年查询 → DuckDB跨文件扫描
    """
    
    def __init__(self, base_path: str = "data/market"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
    
    def _get_path(self, symbol: str, timeframe: str, year: int) -> Path:
        path = self.base_path / symbol / timeframe
        path.mkdir(parents=True, exist_ok=True)
        return path / f"{year}.parquet"
    
    def write(
        self,
        symbol: str,
        timeframe: str,
        df: pd.DataFrame,
        source: str = 'mt5'
    ) -> dict:
        """
        写入Parquet，按年自动分组
        支持增量合并（不重复写入）
        """
        if df.empty:
            return {}
        
        df = df.copy()
        df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
        df['source'] = source
        df['year'] = df['timestamp'].dt.year
        
        results = {}
        for year, group in df.groupby('year'):
            path = self._get_path(symbol, timeframe, year)
            group = group.drop(columns=['year'])
            
            if path.exists():
                # 合并现有数据（去重）
                existing = pq.read_table(str(path)).to_pandas()
                merged = pd.concat([existing, group])
                merged = merged.drop_duplicates(
                    subset=['timestamp'], keep='last'
                ).sort_values('timestamp')
            else:
                merged = group.sort_values('timestamp')
            
            # 转为Arrow Table确保Schema一致
            table = pa.Table.from_pandas(
                merged, schema=OHLCV_SCHEMA, preserve_index=False
            )
            pq.write_table(
                table, str(path),
                compression='snappy',           # 速度和压缩率的平衡
                row_group_size=50000,           # 优化随机读取
                use_dictionary=['source'],      # 字符串列字典编码
            )
            results[year] = len(merged)
        
        return results
    
    def read(
        self,
        symbol: str,
        timeframe: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """
        读取Parquet数据
        自动跨年合并，支持时间范围过滤（列裁剪）
        """
        symbol_path = self.base_path / symbol / timeframe
        if not symbol_path.exists():
            return pd.DataFrame()
        
        parquet_files = sorted(symbol_path.glob("*.parquet"))
        if not parquet_files:
            return pd.DataFrame()
        
        # 按年份过滤文件（减少IO）
        if start or end:
            start_year = start.year if start else 2000
            end_year = end.year if end else 2099
            parquet_files = [
                f for f in parquet_files
                if start_year <= int(f.stem) <= end_year
            ]
        
        if not parquet_files:
            return pd.DataFrame()
        
        # DuckDB扫描多个Parquet文件（极快）
        import duckdb
        file_list = [str(f) for f in parquet_files]
        
        query = f"""
            SELECT timestamp, open, high, low, close, volume, source
            FROM read_parquet({file_list})
            WHERE 1=1
        """
        params = []
        if start:
            query += " AND timestamp >= ?"
            params.append(start)
        if end:
            query += " AND timestamp <= ?"
            params.append(end)
        query += " ORDER BY timestamp ASC"
        
        with duckdb.connect() as conn:
            df = conn.execute(query, params).df()
        
        return df
    
    def get_coverage(self, symbol: str, timeframe: str) -> List[dict]:
        """获取数据覆盖情况"""
        symbol_path = self.base_path / symbol / timeframe
        if not symbol_path.exists():
            return []
        
        result = []
        for f in sorted(symbol_path.glob("*.parquet")):
            meta = pq.read_metadata(str(f))
            result.append({
                "year": int(f.stem),
                "rows": meta.num_rows,
                "size_mb": round(f.stat().st_size / 1024 / 1024, 2)
            })
        return result
    
    def archive_from_duckdb(
        self, 
        duck_db,  # DuckDBManager instance
        symbol: str, 
        timeframe: str
    ) -> int:
        """
        将DuckDB中的历史数据归档到Parquet
        定时任务调用（每日凌晨）
        """
        df = duck_db.get_ohlcv(symbol, timeframe)
        if df.empty:
            return 0
        
        results = self.write(symbol, timeframe, df)
        total = sum(results.values())
        logger.info(f"Archived {total} rows for {symbol}/{timeframe}")
        return total
```

### DuckDB热查询层

```python
# backend/database/duck_db.py
import duckdb
import pandas as pd
from pathlib import Path
from typing import Optional
import threading
import logging

logger = logging.getLogger(__name__)


class DuckDBManager:
    """
    DuckDB管理器 - 热数据查询层
    
    职责：
    1. 存储最近N天实时数据（热存储）
    2. 跨文件扫描Parquet（冷存储代理）
    3. 特征计算的中间层
    
    连接策略：读写分离，避免AI训练锁库
    """
    
    def __init__(
        self, 
        db_path: str = "data/db/market.duckdb",
        parquet_base: str = "data/market"
    ):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self.parquet_base = parquet_base
        self._write_lock = threading.Lock()
        
        # 写连接（单例）
        self._write_conn = duckdb.connect(db_path)
        self._init_schema()
    
    def _get_read_conn(self):
        """
        读连接：每次新建，支持并发
        DuckDB读连接天然并发安全
        """
        return duckdb.connect(self.db_path, read_only=True)
    
    def _init_schema(self):
        self._write_conn.execute("""
            CREATE TABLE IF NOT EXISTS ohlcv_hot (
                symbol      VARCHAR     NOT NULL,
                timeframe   VARCHAR     NOT NULL,
                timestamp   TIMESTAMP   NOT NULL,
                open        DOUBLE      NOT NULL,
                high        DOUBLE      NOT NULL,
                low         DOUBLE      NOT NULL,
                close       DOUBLE      NOT NULL,
                volume      DOUBLE      NOT NULL,
                source      VARCHAR     DEFAULT 'mt5',
                PRIMARY KEY (symbol, timeframe, timestamp)
            )
        """)
        
        # 当前未完成K线（实时更新）
        self._write_conn.execute("""
            CREATE TABLE IF NOT EXISTS current_bar (
                symbol      VARCHAR     NOT NULL,
                timeframe   VARCHAR     NOT NULL,
                timestamp   TIMESTAMP   NOT NULL,
                open        DOUBLE      NOT NULL,
                high        DOUBLE      NOT NULL,
                low         DOUBLE      NOT NULL,
                close       DOUBLE      NOT NULL,
                volume      DOUBLE      NOT NULL,
                updated_at  TIMESTAMP   DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (symbol, timeframe)
            )
        """)
    
    def upsert_bar(
        self, 
        symbol: str, 
        timeframe: str, 
        bar: dict,
        is_closed: bool = False
    ):
        """
        更新单根K线
        未关闭 → current_bar表
        已关闭 → ohlcv_hot表
        """
        with self._write_lock:
            if is_closed:
                self._write_conn.execute("""
                    INSERT OR REPLACE INTO ohlcv_hot 
                    (symbol, timeframe, timestamp, open, high, low, close, volume)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, [
                    symbol, timeframe, bar['timestamp'],
                    bar['open'], bar['high'], bar['low'],
                    bar['close'], bar['volume']
                ])
            else:
                self._write_conn.execute("""
                    INSERT OR REPLACE INTO current_bar
                    (symbol, timeframe, timestamp, open, high, low, 
                     close, volume, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, [
                    symbol, timeframe, bar['timestamp'],
                    bar['open'], bar['high'], bar['low'],
                    bar['close'], bar['volume']
                ])
    
    def query_unified(
        self,
        symbol: str,
        timeframe: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        limit: int = 1000,
        include_current: bool = True
    ) -> pd.DataFrame:
        """
        统一查询接口：自动合并 Parquet历史 + DuckDB热数据
        这是前端和AI Bot的主要查询入口
        """
        parquet_pattern = (
            f"{self.parquet_base}/{symbol}/{timeframe}/*.parquet"
        )
        
        # 检查Parquet文件是否存在
        import glob
        has_parquet = bool(glob.glob(parquet_pattern))
        
        with self._get_read_conn() as conn:
            if has_parquet:
                # 合并Parquet历史 + 热数据
                query = f"""
                    WITH cold AS (
                        SELECT timestamp, open, high, low, close, volume
                        FROM read_parquet('{parquet_pattern}')
                    ),
                    hot AS (
                        SELECT timestamp, open, high, low, close, volume
                        FROM ohlcv_hot
                        WHERE symbol = '{symbol}' AND timeframe = '{timeframe}'
                    )
                    SELECT * FROM cold
                    UNION ALL
                    SELECT * FROM hot
                    WHERE timestamp > (SELECT COALESCE(MAX(timestamp), '1970-01-01') FROM cold)
                """
            else:
                query = f"""
                    SELECT timestamp, open, high, low, close, volume
                    FROM ohlcv_hot
                    WHERE symbol = '{symbol}' AND timeframe = '{timeframe}'
                """
            
            # 包含当前未完成K线
            if include_current:
                query = f"""
                    WITH base AS ({query}),
                    curr AS (
                        SELECT timestamp, open, high, low, close, volume
                        FROM current_bar
                        WHERE symbol = '{symbol}' AND timeframe = '{timeframe}'
                    )
                    SELECT * FROM base
                    UNION ALL
                    SELECT * FROM curr
                    WHERE timestamp > (SELECT MAX(timestamp) FROM base)
                """
            
            # 时间范围过滤
            wrapper = f"SELECT * FROM ({query}) q WHERE 1=1"
            params = []
            if start:
                wrapper += " AND timestamp >= ?"
                params.append(start)
            if end:
                wrapper += " AND timestamp <= ?"
                params.append(end)
            wrapper += f" ORDER BY timestamp DESC LIMIT {limit}"
            wrapper = f"SELECT * FROM ({wrapper}) q2 ORDER BY timestamp ASC"
            
            df = conn.execute(wrapper, params).df()
        
        return df
    
    def get_latest_timestamp(self, symbol: str, timeframe: str) -> Optional[str]:
        with self._get_read_conn() as conn:
            result = conn.execute("""
                SELECT MAX(timestamp) FROM ohlcv_hot
                WHERE symbol = ? AND timeframe = ?
            """, [symbol, timeframe]).fetchone()
        return str(result[0]) if result and result[0] else None
    
    def cleanup_old_data(self, keep_days: int = 30):
        """
        清理热存储中的旧数据（已归档到Parquet的）
        定时任务调用
        """
        with self._write_lock:
            self._write_conn.execute(f"""
                DELETE FROM ohlcv_hot
                WHERE timestamp < NOW() - INTERVAL '{keep_days} days'
            """)
```

---

## 实时数据双通道

```python
# backend/data_sources/mt5_source.py
"""
MT5数据源 - ZMQ Push + Poll双通道
主通道: ZMQ（低延迟，~1ms）
备用通道: Poll（可靠性保障）
"""
import MetaTrader5 as mt5
import zmq
import zmq.asyncio
import asyncio
import pandas as pd
from datetime import datetime
from typing import Callable, Optional
import logging
from .base import BaseDataSource, Timeframe, RealtimeBar

logger = logging.getLogger(__name__)

TF_MAP = {
    Timeframe.M1:  mt5.TIMEFRAME_M1,
    Timeframe.M5:  mt5.TIMEFRAME_M5,
    Timeframe.M15: mt5.TIMEFRAME_M15,
    Timeframe.M30: mt5.TIMEFRAME_M30,
    Timeframe.H1:  mt5.TIMEFRAME_H1,
    Timeframe.H4:  mt5.TIMEFRAME_H4,
    Timeframe.D1:  mt5.TIMEFRAME_D1,
}


class MT5DataSource(BaseDataSource):
    
    ZMQ_PUSH_PORT = 5557  # MT5 EA → Python
    POLL_INTERVAL = {     # 各周期轮询间隔(秒)
        Timeframe.M1:  0.5,
        Timeframe.M5:  1.0,
        Timeframe.M15: 2.0,
        Timeframe.M30: 5.0,
        Timeframe.H1:  10.0,
        Timeframe.H4:  20.0,
        Timeframe.D1:  30.0,
    }
    
    def __init__(self):
        self._connected = False
        self._ctx = zmq.asyncio.Context()
        self._subscriptions: dict = {}
        self._zmq_available = False
        self._callbacks: dict = {}
    
    def connect(self) -> bool:
        if not mt5.initialize():
            logger.error(f"MT5 init failed: {mt5.last_error()}")
            return False
        self._connected = True
        
        # 尝试连接ZMQ（需要MT5端有对应EA运行）
        try:
            self._zmq_pull = self._ctx.socket(zmq.PULL)
            self._zmq_pull.setsockopt(zmq.RCVTIMEO, 100)  # 100ms超时
            self._zmq_pull.connect(f"tcp://localhost:{self.ZMQ_PUSH_PORT}")
            self._zmq_available = True
            logger.info("ZMQ channel connected")
        except Exception as e:
            logger.warning(f"ZMQ unavailable, will use poll: {e}")
            self._zmq_available = False
        
        return True
    
    @property
    def is_connected(self) -> bool:
        return self._connected
    
    def get_historical_data(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        count: int = 5000
    ) -> pd.DataFrame:
        mt5_tf = TF_MAP[timeframe]
        
        if start and end:
            rates = mt5.copy_rates_range(symbol, mt5_tf, start, end)
        elif start:
            rates = mt5.copy_rates_from(symbol, mt5_tf, start, count)
        else:
            rates = mt5.copy_rates_from_pos(symbol, mt5_tf, 0, count)
        
        if rates is None or len(rates) == 0:
            return pd.DataFrame()
        
        df = pd.DataFrame(rates)
        df['timestamp'] = pd.to_datetime(df['time'], unit='s', utc=True)
        df = df.rename(columns={'tick_volume': 'volume'})
        return df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
    
    async def subscribe_realtime(
        self,
        symbol: str,
        timeframe: Timeframe,
        callback: Callable
    ):
        key = f"{symbol}_{timeframe.value}"
        self._callbacks[key] = callback
        
        if key in self._subscriptions:
            self._subscriptions[key].cancel()
        
        if self._zmq_available:
            task = asyncio.create_task(
                self._zmq_channel(symbol, timeframe)
            )
        else:
            task = asyncio.create_task(
                self._poll_channel(symbol, timeframe)
            )
        
        self._subscriptions[key] = task
    
    async def _zmq_channel(self, symbol: str, timeframe: Timeframe):
        """
        ZMQ主通道：接收MT5 EA推送的数据
        EA需要实现对应的ZMQ推送逻辑
        """
        key = f"{symbol}_{timeframe.value}"
        heartbeat_timeout = 5.0     # 5秒无数据切换到Poll
        last_received = asyncio.get_event_loop().time()
        
        while True:
            try:
                # 非阻塞接收
                try:
                    frames = await asyncio.wait_for(
                        self._zmq_pull.recv_multipart(),
                        timeout=1.0
                    )
                    bar = self._parse_zmq_frame(frames)
                    if bar and bar.symbol == symbol:
                        last_received = asyncio.get_event_loop().time()
                        callback = self._callbacks.get(key)
                        if callback:
                            await callback(bar)
                except asyncio.TimeoutError:
                    pass
                
                # 心跳检测：超时自动切换Poll
                elapsed = asyncio.get_event_loop().time() - last_received
                if elapsed > heartbeat_timeout:
                    logger.warning(
                        f"ZMQ timeout for {symbol}, falling back to poll"
                    )
                    await self._poll_channel(symbol, timeframe)
                    return
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"ZMQ channel error: {e}")
                await asyncio.sleep(1)
    
    def _parse_zmq_frame(self, frames: list) -> Optional[RealtimeBar]:
        """解析ZMQ数据帧"""
        try:
            import json
            data = json.loads(frames[0])
            return RealtimeBar(
                symbol=data['symbol'],
                timeframe=data['timeframe'],
                timestamp=data['time'],
                open=data['open'],
                high=data['high'],
                low=data['low'],
                close=data['close'],
                volume=data['volume'],
                is_closed=data.get('is_closed', False),
                source='mt5_zmq'
            )
        except Exception:
            return None
    
    async def _poll_channel(self, symbol: str, timeframe: Timeframe):
        """
        Poll备用通道：主动轮询MT5
        """
        key = f"{symbol}_{timeframe.value}"
        interval = self.POLL_INTERVAL.get(timeframe, 2.0)
        last_bar_time = None
        
        logger.info(f"Poll channel started: {symbol} {timeframe}")
        
        while True:
            try:
                rates = mt5.copy_rates_from_pos(
                    symbol, TF_MAP[timeframe], 0, 2
                )
                
                if rates is not None and len(rates) > 0:
                    latest = rates[-1]
                    prev   = rates[-2] if len(rates) > 1 else None
                    
                    current_time = latest['time']
                    is_new_bar   = (
                        last_bar_time is not None and 
                        current_time != last_bar_time
                    )
                    
                    # 推送已关闭的前一根K线
                    if is_new_bar and prev is not None:
                        closed_bar = RealtimeBar(
                            symbol=symbol,
                            timeframe=timeframe.value,
                            timestamp=int(prev['time']),
                            open=float(prev['open']),
                            high=float(prev['high']),
                            low=float(prev['low']),
                            close=float(prev['close']),
                            volume=float(prev['tick_volume']),
                            is_closed=True,
                            source='mt5_poll'
                        )
                        callback = self._callbacks.get(key)
                        if callback:
                            await callback(closed_bar)
                    
                    # 推送当前K线更新
                    current_bar = RealtimeBar(
                        symbol=symbol,
                        timeframe=timeframe.value,
                        timestamp=int(current_time),
                        open=float(latest['open']),
                        high=float(latest['high']),
                        low=float(latest['low']),
                        close=float(latest['close']),
                        volume=float(latest['tick_volume']),
                        is_closed=False,
                        source='mt5_poll'
                    )
                    callback = self._callbacks.get(key)
                    if callback:
                        await callback(current_bar)
                    
                    last_bar_time = current_time
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Poll error {symbol}: {e}")
            
            await asyncio.sleep(interval)
    
    def disconnect(self):
        for task in self._subscriptions.values():
            task.cancel()
        self._subscriptions.clear()
        if hasattr(self, '_zmq_pull'):
            self._zmq_pull.close()
        mt5.shutdown()
        self._connected = False
    
    def get_symbols(self):
        symbols = mt5.symbols_get()
        if not symbols:
            return []
        from .base import SymbolInfo
        return [
            SymbolInfo(
                symbol=s.name,
                description=s.description,
                category=self._get_category(s.path, s.name),
                digits=s.digits,
                point=s.point,
                contract_size=s.trade_contract_size,
            )
            for s in symbols
        ]
    
    def _get_category(self, path: str, name: str) -> str:
        path_l = path.lower()
        if 'forex' in path_l: return 'Forex'
        if 'metal' in path_l or name in ['XAUUSD','XAGUSD']: return 'Metals'
        if 'crypto' in path_l: return 'Crypto'
        if 'index' in path_l or 'indices' in path_l: return 'Indices'
        if 'stock' in path_l: return 'Stocks'
        return 'Other'
    
    def unsubscribe(self, symbol: str, timeframe: Timeframe):
        key = f"{symbol}_{timeframe.value}"
        if key in self._subscriptions:
            self._subscriptions[key].cancel()
            del self._subscriptions[key]
```

---

## AI Bot数据客户端

```python
# ai_bot/data_client.py
"""
AI Bot专用数据客户端
独立进程运行，通过ZMQ订阅数据
"""
import zmq
import zmq.asyncio
import asyncio
import pandas as pd
import numpy as np
import duckdb
import json
from typing import Callable, Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class BotDataClient:
    """
    AI Bot数据接入客户端
    
    功能：
    1. 订阅实时市场数据
    2. 查询历史数据（Parquet + DuckDB）
    3. 请求特征计算
    """
    
    def __init__(
        self,
        backend_host: str = "localhost",
        parquet_base: str = "data/market"
    ):
        self.backend_host = backend_host
        self.parquet_base = parquet_base
        self.ctx = zmq.asyncio.Context()
        self._handlers: dict = {}
    
    def subscribe_realtime(
        self,
        symbol: str,
        timeframe: str,
        handler: Callable
    ):
        """注册实时数据处理器"""
        key = f"{symbol}_{timeframe}"
        self._handlers[key] = handler
    
    async def start_listening(self):
        """启动实时数据监听"""
        sub = self.ctx.socket(zmq.SUB)
        sub.connect(f"tcp://{self.backend_host}:5555")
        
        # 只订阅已注册的主题
        for key in self._handlers:
            symbol, tf = key.rsplit('_', 1)
            for topic in ['BAR', 'CLOSED']:
                sub.setsockopt_string(
                    zmq.SUBSCRIBE, f"{topic}.{symbol}.{tf}"
                )
        
        logger.info(f"Bot listening on {len(self._handlers)} subscriptions")
        
        while True:
            try:
                frames = await sub.recv_multipart()
                topic_str = frames[0].decode()
                data = json.loads(frames[1])
                
                # 路由到对应处理器
                parts = topic_str.split('.')
                if len(parts) >= 3:
                    _, symbol, tf = parts[0], parts[1], parts[2]
                    key = f"{symbol}_{tf}"
                    handler = self._handlers.get(key)
                    if handler:
                        await handler(data)
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Bot listener error: {e}")
    
    def get_historical(
        self,
        symbol: str,
        timeframe: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        as_features: bool = False
    ) -> pd.DataFrame:
        """
        获取历史数据
        直接读取Parquet，不经过后端HTTP（零拷贝）
        """
        pattern = f"{self.parquet_base}/{symbol}/{timeframe}/*.parquet"
        
        import glob
        files = sorted(glob.glob(pattern))
        
        if not files:
            logger.warning(f"No parquet files for {symbol}/{timeframe}")
            return pd.DataFrame()
        
        query = f"""
            SELECT timestamp, open, high, low, close, volume
            FROM read_parquet({files})
            WHERE 1=1
        """
        params = []
        if start:
            query += " AND timestamp >= ?"
            params.append(start)
        if end:
            query += " AND timestamp <= ?"
            params.append(end)
        query += " ORDER BY timestamp ASC"
        
        with duckdb.connect() as conn:
            df = conn.execute(query, params).df()
        
        if as_features:
            df = self._compute_features(df)
        
        return df
    
    def _compute_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        内置基础特征计算
        复杂特征由 feature_pipeline.py 处理
        """
        df = df.copy()
        c = df['close']
        
        # 价格特征
        df['returns']      = c.pct_change()
        df['log_returns']  = np.log(c / c.shift(1))
        df['hl_ratio']     = (df['high'] - df['low']) / df['close']
        df['co_ratio']     = (df['close'] - df['open']) / df['open']
        
        # 移动平均
        for period in [5, 10, 20, 50, 200]:
            df[f'sma_{period}'] = c.rolling(period).mean()
            df[f'ema_{period}'] = c.ewm(span=period).mean()
        
        # 波动率
        df['volatility_20'] = df['returns'].rolling(20).std() * np.sqrt(252)
        
        # 成交量特征
        df['volume_sma_20'] = df['volume'].rolling(20).mean()
        df['volume_ratio']  = df['volume'] / df['volume_sma_20']
        
        # ATR
        df['tr'] = np.maximum(
            df['high'] - df['low'],
            np.maximum(
                abs(df['high'] - c.shift(1)),
                abs(df['low']  - c.shift(1))
            )
        )
        df['atr_14'] = df['tr'].rolling(14).mean()
        
        return df.dropna()
```

```python
# ai_bot/feature_pipeline.py
"""
特征工程管道
支持训练/推理两种模式，防止数据泄露
"""
import pandas as pd
import numpy as np
from sklearn.preprocessing import RobustScaler
import joblib
from pathlib import Path
from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class FeaturePipeline:
    """
    特征管道
    
    训练模式：fit_transform，保存scaler
    推理模式：transform（使用已保存的scaler）
    
    关键原则：
    1. 所有特征只使用历史数据（无未来泄露）
    2. Scaler在训练集上fit，推理时复用
    3. 时间序列分割（非随机）
    """
    
    def __init__(self, model_dir: str = "ai_bot/models/saved"):
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.scaler: Optional[RobustScaler] = None
        self.feature_cols: Optional[list] = None
    
    def build_features(
        self, 
        df: pd.DataFrame,
        sequence_length: int = 60    # LSTM序列长度
    ) -> pd.DataFrame:
        """
        构建完整特征集
        所有特征都是严格因果的（不使用未来数据）
        """
        df = df.copy().sort_values('timestamp')
        c = df['close']
        h = df['high']
        l = df['low']
        v = df['volume']
        
        # ======= 价格特征 =======
        df['ret_1']  = c.pct_change(1)
        df['ret_5']  = c.pct_change(5)
        df['ret_20'] = c.pct_change(20)
        
        # ======= 趋势特征 =======
        for p in [5, 10, 20, 50]:
            ema = c.ewm(span=p, adjust=False).mean()
            df[f'ema_ratio_{p}'] = c / ema - 1  # 价格偏离EMA的程度
        
        # ======= 波动率特征 =======
        df['realized_vol_5']  = df['ret_1'].rolling(5).std()
        df['realized_vol_20'] = df['ret_1'].rolling(20).std()
        df['vol_ratio']       = df['realized_vol_5'] / df['realized_vol_20']
        
        # ATR标准化
        tr = pd.concat([
            h - l,
            (h - c.shift(1)).abs(),
            (l - c.shift(1)).abs()
        ], axis=1).max(axis=1)
        df['atr_ratio'] = tr.rolling(14).mean() / c
        
        # ======= 成交量特征 =======
        df['vol_ret']    = v.pct_change()
        df['vol_ratio']  = v / v.rolling(20).mean()
        df['vwap_ratio'] = c / (v * c).rolling(20).sum() * v.rolling(20).sum()
        
        # ======= 动量特征 =======
        # RSI
        delta = c.diff()
        gain  = delta.clip(lower=0).rolling(14).mean()
        loss  = (-delta.clip(upper=0)).rolling(14).mean()
        df['rsi'] = 100 - (100 / (1 + gain / loss.replace(0, np.nan)))
        df['rsi'] = df['rsi'] / 100  # 标准化到[0,1]
        
        # Stochastic
        lowest  = l.rolling(14).min()
        highest = h.rolling(14).max()
        df['stoch_k'] = (c - lowest) / (highest - lowest + 1e-10)
        
        # ======= 市场结构特征 =======
        df['higher_high'] = (
            (h > h.shift(1)) & (h.shift(1) > h.shift(2))
        ).astype(float)
        df['lower_low'] = (
            (l < l.shift(1)) & (l.shift(1) < l.shift(2))
        ).astype(float)
        
        # 去掉NaN
        df = df.dropna()
        
        # 记录特征列
        exclude = ['timestamp', 'open', 'high', 'low', 'close', 
                   'volume', 'source']
        self.feature_cols = [c for c in df.columns if c not in exclude]
        
        return df
    
    def time_series_split(
        self,
        df: pd.DataFrame,
        train_ratio: float = 0.7,
        val_ratio: float = 0.15
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        时间序列分割（严格按时间顺序）
        不能随机分割！会导致未来数据泄露
        """
        n = len(df)
        train_end = int(n * train_ratio)
        val_end   = int(n * (train_ratio + val_ratio))
        
        train = df.iloc[:train_end]
        val   = df.iloc[train_end:val_end]
        test  = df.iloc[val_end:]
        
        logger.info(
            f"Split: train={len(train)} val={len(val)} test={len(test)}"
        )
        return train, val, test
    
    def fit_transform(self, df: pd.DataFrame) -> np.ndarray:
        """训练模式：fit scaler并transform"""
        features = df[self.feature_cols].values
        self.scaler = RobustScaler()  # 对异常值更鲁棒
        scaled = self.scaler.fit_transform(features)
        
        # 保存scaler
        joblib.dump(
            self.scaler, 
            self.model_dir / 'scaler.pkl'
        )
        return scaled
    
    def transform(self, df: pd.DataFrame) -> np.ndarray:
        """推理模式：使用已有scaler"""
        if self.scaler is None:
            self.scaler = joblib.load(self.model_dir / 'scaler.pkl')
        return self.scaler.transform(df[self.feature_cols].values)
    
    def make_sequences(
        self,
        data: np.ndarray,
        seq_len: int = 60,
        target_offset: int = 1  # 预测未来第N根K线
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        构建LSTM序列样本
        X: (samples, seq_len, features)
        y: 未来收益方向 {0: 下跌, 1: 上涨}
        """
        X, y = [], []
        close_idx = self.feature_cols.index('ret_1') \
                    if 'ret_1' in self.feature_cols else 0
        
        for i in range(seq_len, len(data) - target_offset):
            X.append(data[i-seq_len:i])
            future_ret = data[i + target_offset - 1][close_idx]
            y.append(1 if future_ret > 0 else 0)
        
        return np.array(X), np.array(y)
```

---

## 系统启动和监控

```python
# backend/main.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio
import logging

from .core.message_bus import MessageBus, MessageBusSubscriber, Topic
from .core.event_store import EventStore
from .database.duck_db import DuckDBManager
from .database.parquet_store import ParquetStore
from .database.sqlite_db import SQLiteManager
from .data_sources.mt5_source import MT5DataSource
from .services.ingestion import IngestionService
from .services.historical import HistoricalDataService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
)

# ========== 全局组件 ==========
message_bus    = MessageBus()
event_store    = EventStore()
duck_db        = DuckDBManager()
parquet_store  = ParquetStore()
sqlite_db      = SQLiteManager()
mt5_source     = MT5DataSource()

ingestion_svc  = IngestionService(
    source=mt5_source,
    duck_db=duck_db,
    parquet_store=parquet_store,
    message_bus=message_bus,
    event_store=event_store
)
historical_svc = HistoricalDataService(duck_db, parquet_store, sqlite_db)

# WebSocket连接管理
ws_subscribers: dict = {}  # key → set[WebSocket]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ===== 启动 =====
    await message_bus.start()
    
    if mt5_source.connect():
        # 同步Symbol列表
        symbols = mt5_source.get_symbols()
        sqlite_db.upsert_symbols([
            {
                'symbol': s.symbol,
                'description': s.description,
                'category': s.category,
                'digits': s.digits,
                'point': s.point,
                'contract_size': s.contract_size,
                'metadata': '{}'
            }
            for s in symbols
        ])
    
    # 启动Parquet定时归档任务
    archive_task = asyncio.create_task(_archive_loop())
    
    yield
    
    # ===== 关闭 =====
    archive_task.cancel()
    mt5_source.disconnect()
    message_bus.stop()


async def _archive_loop():
    """每日凌晨将DuckDB热数据归档到Parquet"""
    while True:
        await asyncio.sleep(3600)  # 每小时检查一次
        # TODO: 检查是否需要归档


app = FastAPI(title="Trading Platform", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ========== REST API ==========

@app.get("/api/health")
async def health():
    return {
        "mt5": mt5_source.is_connected,
        "duckdb": True,
        "message_bus": message_bus._running
    }

@app.get("/api/symbols")
async def get_symbols(
    category: str = None,
    search: str = None,
    favorites_only: bool = False
):
    return {"symbols": sqlite_db.get_symbols(category, favorites_only, search)}

@app.get("/api/historical/{symbol}/{timeframe}")
async def get_historical(
    symbol: str,
    timeframe: str,
    start: str = None,
    end: str = None,
    limit: int = 1000,
    force_fetch: bool = False
):
    return await historical_svc.get_data(
        symbol, timeframe, start, end, limit, force_fetch
    )

@app.get("/api/coverage/{symbol}/{timeframe}")
async def get_coverage(symbol: str, timeframe: str):
    """查询数据覆盖情况"""
    return {
        "parquet": parquet_store.get_coverage(symbol, timeframe),
        "hot": duck_db.get_data_info(symbol, timeframe) 
               if hasattr(duck_db, 'get_data_info') else {}
    }

@app.post("/api/subscribe/{symbol}/{timeframe}")
async def subscribe_realtime(symbol: str, timeframe: str):
    """触发实时订阅（供AI Bot HTTP调用）"""
    from .data_sources.base import Timeframe as TF
    await ingestion_svc.start_realtime(symbol, TF(timeframe))
    return {"status": "subscribed", "symbol": symbol, "timeframe": timeframe}


# ========== WebSocket ==========

class FrontendSubscriber(MessageBusSubscriber):
    """前端WebSocket消息转发器"""
    
    async def on_message(self, msg):
        key = f"{msg.symbol}_{msg.timeframe}"
        sockets = ws_subscribers.get(key, set())
        dead = set()
        
        for ws in sockets:
            try:
                await ws.send_json({
                    "type": msg.topic,
                    "symbol": msg.symbol,
                    "timeframe": msg.timeframe,
                    "bar": msg.payload,
                    "source": msg.source,
                    "seq": msg.seq
                })
            except Exception:
                dead.add(ws)
        
        if dead:
            ws_subscribers[key] -= dead

frontend_sub = FrontendSubscriber()


@app.websocket("/ws/chart")
async def ws_chart(websocket: WebSocket):
    await websocket.accept()
    my_subs = []
    
    try:
        while True:
            data = await websocket.receive_json()
            action    = data.get("action")
            symbol    = data.get("symbol")
            timeframe = data.get("timeframe", "H1")
            
            if action == "subscribe":
                key = f"{symbol}_{timeframe}"
                if key not in ws_subscribers:
                    ws_subscribers[key] = set()
                ws_subscribers[key].add(websocket)
                my_subs.append(key)
                
                # 触发数据摄入
                from .data_sources.base import Timeframe as TF
                await ingestion_svc.start_realtime(symbol, TF(timeframe))
                
                await websocket.send_json({
                    "type": "SUBSCRIBED",
                    "symbol": symbol,
                    "timeframe": timeframe
                })
            
            elif action == "unsubscribe":
                key = f"{symbol}_{timeframe}"
                if key in ws_subscribers:
                    ws_subscribers[key].discard(websocket)
    
    except WebSocketDisconnect:
        for key in my_subs:
            ws_subscribers.get(key, set()).discard(websocket)
```

---

## 完整数据流向图

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                    数据流向总览
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MetaTrader 5
   │
   ├─[ZMQ PUSH]────────────────────────────────────┐
   │                                                │
   └─[MT5 API Poll]─────────────────────────────── │
                                                    ▼
                                          IngestionService
                                                    │
                              ┌─────────────────────┼────────────────────┐
                              ▼                     ▼                    ▼
                         EventStore           DuckDB(热)          MessageBus
                         (SQLite)             当前K线              ZMQ PUB
                         完整事件历史          最近30天                 │
                              │                     │              ┌─────┴──────┐
                              │                [定时归档]          ▼            ▼
                              │                     │      FrontendGW      AI Bot
                              │                     ▼      WebSocket SUB   ZMQ SUB
                              │              Parquet(冷)        │              │
                              │              按年分割            ▼              ▼
                              │                            前端图表      信号生成
                              │                                         风险控制
                              │                                              │
                              │                                    ┌─────────┘
                              ▼                                    ▼
                         AI Bot回放                          MT5 执行订单
                         历史验证

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                      查询路径
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

前端/Bot 查询历史数据:
  请求 → DuckDB.query_unified()
            ├── Parquet(历史) ←── DuckDB scan (零拷贝)
            ├── DuckDB热存储
            └── current_bar(当前K线)
          → 合并返回（毫秒级）
```

---

## 关键设计决策汇总

```
┌─────────────────┬────────────────────────────────────┐
│ 问题            │ 解决方案                            │
├─────────────────┼────────────────────────────────────┤
│ AI训练锁库      │ DuckDB读写分离连接                  │
│ 多消费者抢消息  │ ZMQ PUB/SUB，消息总线广播           │
│ 数据泄露风险    │ 严格时间序列分割，因果特征           │
│ ZMQ断线         │ 心跳检测+自动回退Poll               │
│ 回测一致性      │ EventStore事件溯源，可精确回放       │
│ 跨年查询慢      │ DuckDB直接scan多Parquet文件         │
│ 特征重复计算    │ Parquet特征缓存层                   │
│ Bot推理延迟     │ 直读Parquet，不过HTTP               │
└─────────────────┴────────────────────────────────────┘
```

二次补充及修改：
# 数据架构深度设计：冷热分离 + 智能同步

## 首先，对你方案的分析和建议

你的思路非常清晰，我完全同意核心方向，但有几点值得深入讨论：

```
你的方案核心：
├── 热数据 → DuckDB（当月）
├── 冷数据 → Parquet（按月归档）
├── APP启动 → 拉取缺失数据
└── 图表打开 → 检查并补全数据

需要补充考虑的问题：
├── 1. DuckDB当月数据 和 Parquet的边界怎么界定？
│      → 建议：以"已完成的自然月"为Parquet，当月留DuckDB
├── 2. 归档时机：谁触发？什么时候执行？
│      → 建议：月末自动归档 + 手动触发
├── 3. 跨月查询：需要同时读DuckDB + Parquet
│      → DuckDB可以直接 scan Parquet，天然支持
├── 4. 数据状态检查的粒度？
│      → 建议：以月为单位记录 metadata，不要每根K线检查
└── 5. 首次启动 vs 日常启动的处理差异？
       → 建议：分开处理，首次做全量，日常做增量
```

---

## 数据状态机设计

```
每个 (Symbol, Timeframe, YearMonth) 的状态：

  MISSING ──拉取──→ SYNCING ──完成──→ HOT(DuckDB)
                                           │
                              月末/手动归档 ↓
                                       ARCHIVING
                                           │
                                      完成 ↓
                                    COLD(Parquet)
                                           │
                              发现数据缺口 ↓
                                      REPAIRING
```

---

## 完整项目结构

```
trading-platform/
├── data/
│   ├── market/
│   │   ├── parquet/                    # 冷数据
│   │   │   ├── EURUSD/
│   │   │   │   ├── H1/
│   │   │   │   │   ├── 2024_01.parquet
│   │   │   │   │   ├── 2024_02.parquet
│   │   │   │   │   └── 2024_03.parquet
│   │   │   │   └── M1/
│   │   │   └── XAUUSD/
│   │   └── duckdb/
│   │       └── hot.duckdb              # 热数据（当月+进行中）
│   └── meta/
│       └── sync_meta.db               # SQLite：同步状态元数据
│
└── backend/
    ├── main.py
    ├── config.py
    ├── database/
    │   ├── hot_store.py                # DuckDB热存储
    │   ├── cold_store.py               # Parquet冷存储
    │   ├── meta_store.py               # SQLite元数据/状态
    │   └── unified_query.py            # 统一查询门面
    ├── sync/
    │   ├── sync_manager.py             # 同步总调度
    │   ├── gap_detector.py             # 数据缺口检测
    │   └── archiver.py                 # 归档服务
    ├── data_sources/
    │   ├── base.py
    │   └── mt5_source.py
    ├── realtime/
    │   ├── ingestion.py                # 实时数据写入
    │   └── zmq_listener.py
    └── api/
        ├── routes.py
        └── websocket.py
```

---

## 元数据层（核心状态管理）

```python
# backend/database/meta_store.py
"""
同步状态元数据管理
这是整个数据系统的"账本"，记录每块数据的状态
"""
import sqlite3
import json
from pathlib import Path
from datetime import datetime, date
from typing import Optional, List
from dataclasses import dataclass
from enum import Enum


class DataStatus(str, Enum):
    MISSING    = "MISSING"      # 完全没有数据
    SYNCING    = "SYNCING"      # 正在拉取
    HOT        = "HOT"          # 在DuckDB中（当月或未归档）
    ARCHIVING  = "ARCHIVING"    # 正在归档
    COLD       = "COLD"         # 已归档到Parquet
    REPAIRING  = "REPAIRING"    # 发现缺口，正在修复
    ERROR      = "ERROR"        # 同步失败


@dataclass
class MonthlyDataBlock:
    """
    数据块：以 (symbol, timeframe, year, month) 为最小管理单位
    """
    symbol:         str
    timeframe:      str
    year:           int
    month:          int
    status:         DataStatus
    bar_count:      int = 0
    first_bar:      Optional[str] = None    # ISO格式时间
    last_bar:       Optional[str] = None
    expected_bars:  int = 0                 # 理论应有K线数
    parquet_path:   Optional[str] = None
    last_sync:      Optional[str] = None
    error_msg:      Optional[str] = None

    @property
    def year_month(self) -> str:
        return f"{self.year:04d}_{self.month:02d}"

    @property
    def is_current_month(self) -> bool:
        now = datetime.now()
        return self.year == now.year and self.month == now.month

    @property
    def completeness(self) -> float:
        """数据完整度 0.0~1.0"""
        if self.expected_bars == 0:
            return 0.0
        return min(self.bar_count / self.expected_bars, 1.0)


# 各周期每月理论K线数（用于完整性检查）
EXPECTED_BARS_PER_MONTH = {
    "M1":  30 * 24 * 60,       # ~43200（含周末会少）
    "M5":  30 * 24 * 12,       # ~8640
    "M15": 30 * 24 * 4,        # ~2880
    "M30": 30 * 24 * 2,        # ~1440
    "H1":  30 * 24,            # ~720
    "H4":  30 * 6,             # ~180
    "D1":  22,                 # 约22个交易日
    "W1":  5,
    "MN1": 1,
}


class MetaStore:
    """
    元数据存储
    记录每个月份数据块的同步状态
    """

    def __init__(self, db_path: str = "data/meta/sync_meta.db"):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._init()

    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS data_blocks (
                    symbol          TEXT    NOT NULL,
                    timeframe       TEXT    NOT NULL,
                    year            INTEGER NOT NULL,
                    month           INTEGER NOT NULL,
                    status          TEXT    NOT NULL DEFAULT 'MISSING',
                    bar_count       INTEGER DEFAULT 0,
                    first_bar       TEXT,
                    last_bar        TEXT,
                    expected_bars   INTEGER DEFAULT 0,
                    parquet_path    TEXT,
                    last_sync       TEXT,
                    error_msg       TEXT,
                    PRIMARY KEY (symbol, timeframe, year, month)
                );

                CREATE TABLE IF NOT EXISTS sync_log (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol      TEXT    NOT NULL,
                    timeframe   TEXT    NOT NULL,
                    year        INTEGER NOT NULL,
                    month       INTEGER NOT NULL,
                    action      TEXT    NOT NULL,   -- FETCH/ARCHIVE/REPAIR
                    started_at  TEXT    NOT NULL,
                    finished_at TEXT,
                    bars_added  INTEGER DEFAULT 0,
                    status      TEXT,               -- OK/FAILED/PARTIAL
                    detail      TEXT
                );

                CREATE TABLE IF NOT EXISTS symbols_meta (
                    symbol          TEXT PRIMARY KEY,
                    description     TEXT,
                    category        TEXT,
                    digits          INTEGER,
                    point           REAL,
                    contract_size   REAL,
                    is_favorite     INTEGER DEFAULT 0,
                    metadata        TEXT,
                    last_seen       TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_blocks_lookup
                ON data_blocks(symbol, timeframe, status);
            """)

    # ─────────────────────────────────────────────
    #  数据块 CRUD
    # ─────────────────────────────────────────────

    def get_block(
        self,
        symbol: str,
        timeframe: str,
        year: int,
        month: int
    ) -> Optional[MonthlyDataBlock]:
        with self._conn() as conn:
            row = conn.execute("""
                SELECT * FROM data_blocks
                WHERE symbol=? AND timeframe=? AND year=? AND month=?
            """, [symbol, timeframe, year, month]).fetchone()

        if not row:
            return None
        return self._row_to_block(row)

    def upsert_block(self, block: MonthlyDataBlock):
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO data_blocks
                (symbol, timeframe, year, month, status, bar_count,
                 first_bar, last_bar, expected_bars, parquet_path,
                 last_sync, error_msg)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(symbol, timeframe, year, month) DO UPDATE SET
                    status        = excluded.status,
                    bar_count     = excluded.bar_count,
                    first_bar     = excluded.first_bar,
                    last_bar      = excluded.last_bar,
                    expected_bars = excluded.expected_bars,
                    parquet_path  = excluded.parquet_path,
                    last_sync     = excluded.last_sync,
                    error_msg     = excluded.error_msg
            """, [
                block.symbol, block.timeframe,
                block.year, block.month,
                block.status.value,
                block.bar_count,
                block.first_bar, block.last_bar,
                block.expected_bars,
                block.parquet_path,
                block.last_sync,
                block.error_msg
            ])

    def update_status(
        self,
        symbol: str,
        timeframe: str,
        year: int,
        month: int,
        status: DataStatus,
        **kwargs
    ):
        """快速更新状态，附带可选字段"""
        block = self.get_block(symbol, timeframe, year, month)
        if not block:
            block = MonthlyDataBlock(
                symbol=symbol, timeframe=timeframe,
                year=year, month=month, status=status,
                expected_bars=EXPECTED_BARS_PER_MONTH.get(timeframe, 0)
            )
        else:
            block.status = status

        for k, v in kwargs.items():
            if hasattr(block, k):
                setattr(block, k, v)

        block.last_sync = datetime.now().isoformat()
        self.upsert_block(block)

    def get_all_blocks(
        self,
        symbol: str,
        timeframe: str
    ) -> List[MonthlyDataBlock]:
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT * FROM data_blocks
                WHERE symbol=? AND timeframe=?
                ORDER BY year, month
            """, [symbol, timeframe]).fetchall()
        return [self._row_to_block(r) for r in rows]

    def get_missing_months(
        self,
        symbol: str,
        timeframe: str,
        from_year_month: tuple,         # (year, month)
        to_year_month: tuple            # (year, month) inclusive
    ) -> List[tuple]:
        """
        返回在 [from, to] 范围内，
        状态为 MISSING 或 ERROR 的月份列表
        """
        existing = {
            (b.year, b.month): b
            for b in self.get_all_blocks(symbol, timeframe)
        }

        missing = []
        y, m = from_year_month
        ey, em = to_year_month

        while (y, m) <= (ey, em):
            block = existing.get((y, m))
            if not block or block.status in (
                DataStatus.MISSING, DataStatus.ERROR
            ):
                missing.append((y, m))
            m += 1
            if m > 12:
                m = 1
                y += 1

        return missing

    def get_cold_months(
        self, symbol: str, timeframe: str
    ) -> List[MonthlyDataBlock]:
        """获取已归档的月份"""
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT * FROM data_blocks
                WHERE symbol=? AND timeframe=? AND status='COLD'
                ORDER BY year, month
            """, [symbol, timeframe]).fetchall()
        return [self._row_to_block(r) for r in rows]

    # ─────────────────────────────────────────────
    #  日志
    # ─────────────────────────────────────────────

    def log_sync_start(
        self,
        symbol: str, timeframe: str,
        year: int, month: int,
        action: str
    ) -> int:
        """返回log_id"""
        with self._conn() as conn:
            cursor = conn.execute("""
                INSERT INTO sync_log
                (symbol, timeframe, year, month, action, started_at)
                VALUES (?,?,?,?,?,?)
            """, [
                symbol, timeframe, year, month,
                action, datetime.now().isoformat()
            ])
            return cursor.lastrowid

    def log_sync_finish(
        self,
        log_id: int,
        bars_added: int,
        status: str,
        detail: str = ""
    ):
        with self._conn() as conn:
            conn.execute("""
                UPDATE sync_log SET
                    finished_at = ?,
                    bars_added  = ?,
                    status      = ?,
                    detail      = ?
                WHERE id = ?
            """, [
                datetime.now().isoformat(),
                bars_added, status, detail, log_id
            ])

    def _row_to_block(self, row) -> MonthlyDataBlock:
        return MonthlyDataBlock(
            symbol        = row['symbol'],
            timeframe     = row['timeframe'],
            year          = row['year'],
            month         = row['month'],
            status        = DataStatus(row['status']),
            bar_count     = row['bar_count'] or 0,
            first_bar     = row['first_bar'],
            last_bar      = row['last_bar'],
            expected_bars = row['expected_bars'] or 0,
            parquet_path  = row['parquet_path'],
            last_sync     = row['last_sync'],
            error_msg     = row['error_msg'],
        )
```

---

## 热存储层

```python
# backend/database/hot_store.py
"""
DuckDB 热存储
职责：存储当月及尚未归档的数据
写入优化：批量写入，WAL模式
"""
import duckdb
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Optional, List
import threading
import logging

logger = logging.getLogger(__name__)


class HotStore:
    """
    DuckDB热存储管理器

    表结构设计：
    - ohlcv         : 已确认关闭的K线（持久化）
    - current_bar   : 当前正在形成的K线（每Tick更新）
    - write_buffer  : 批量写入缓冲（内存表，定期flush）
    """

    # 缓冲区大小：积累多少根K线后批量写入
    BUFFER_FLUSH_SIZE = 100
    # 缓冲区时间：最多等待多少秒强制flush
    BUFFER_FLUSH_INTERVAL = 5.0

    def __init__(self, db_path: str = "data/market/duckdb/hot.duckdb"):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._lock = threading.Lock()

        # 写连接（单例，串行写入）
        self._wconn = duckdb.connect(db_path)
        self._wconn.execute("PRAGMA threads=4")

        # 内存写缓冲
        self._buffer: List[dict] = []
        self._last_flush = datetime.now().timestamp()

        self._init_schema()
        logger.info(f"HotStore initialized: {db_path}")

    def _init_schema(self):
        self._wconn.executescript("""
            CREATE TABLE IF NOT EXISTS ohlcv (
                symbol      VARCHAR     NOT NULL,
                timeframe   VARCHAR     NOT NULL,
                timestamp   TIMESTAMPTZ NOT NULL,
                open        DOUBLE      NOT NULL,
                high        DOUBLE      NOT NULL,
                low         DOUBLE      NOT NULL,
                close       DOUBLE      NOT NULL,
                volume      DOUBLE      NOT NULL,
                source      VARCHAR     DEFAULT 'mt5',
                PRIMARY KEY (symbol, timeframe, timestamp)
            );

            CREATE TABLE IF NOT EXISTS current_bar (
                symbol      VARCHAR     NOT NULL,
                timeframe   VARCHAR     NOT NULL,
                timestamp   TIMESTAMPTZ NOT NULL,
                open        DOUBLE      NOT NULL,
                high        DOUBLE      NOT NULL,
                low         DOUBLE      NOT NULL,
                close       DOUBLE      NOT NULL,
                volume      DOUBLE      NOT NULL,
                tick_count  INTEGER     DEFAULT 0,
                updated_at  TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (symbol, timeframe)
            );
        """)

    # ─────────────────────────────────────────────
    #  写入接口
    # ─────────────────────────────────────────────

    def update_current_bar(self, symbol: str, timeframe: str, bar: dict):
        """
        更新当前正在形成的K线
        高频调用（每个Tick），使用INSERT OR REPLACE
        """
        with self._lock:
            self._wconn.execute("""
                INSERT OR REPLACE INTO current_bar
                (symbol, timeframe, timestamp, open, high, low,
                 close, volume, tick_count, updated_at)
                VALUES (?,?,?,?,?,?,?,?,
                    COALESCE(
                        (SELECT tick_count+1 FROM current_bar
                         WHERE symbol=? AND timeframe=?), 1
                    ),
                    CURRENT_TIMESTAMP
                )
            """, [
                symbol, timeframe,
                bar['timestamp'],
                bar['open'], bar['high'],
                bar['low'],  bar['close'],
                bar['volume'],
                symbol, timeframe           # for COALESCE subquery
            ])

    def buffer_closed_bar(self, symbol: str, timeframe: str, bar: dict):
        """
        缓冲已关闭K线
        不立即写入磁盘，积累到阈值后批量flush
        """
        entry = {
            'symbol':    symbol,
            'timeframe': timeframe,
            **bar
        }
        self._buffer.append(entry)

        # 判断是否需要flush
        now = datetime.now().timestamp()
        size_trigger = len(self._buffer) >= self.BUFFER_FLUSH_SIZE
        time_trigger = (now - self._last_flush) >= self.BUFFER_FLUSH_INTERVAL

        if size_trigger or time_trigger:
            self._flush_buffer()

    def _flush_buffer(self):
        """批量将缓冲区写入DuckDB"""
        if not self._buffer:
            return

        batch = self._buffer.copy()
        self._buffer.clear()
        self._last_flush = datetime.now().timestamp()

        df = pd.DataFrame(batch)
        df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)

        with self._lock:
            # 高效批量upsert
            self._wconn.execute("""
                INSERT OR REPLACE INTO ohlcv
                SELECT
                    symbol, timeframe, timestamp,
                    open, high, low, close, volume,
                    COALESCE(source, 'mt5')
                FROM df
            """)

        logger.debug(f"Flushed {len(batch)} bars to DuckDB")

    def force_flush(self):
        """强制flush缓冲区（APP关闭时调用）"""
        self._flush_buffer()

    def bulk_write(
        self,
        symbol: str,
        timeframe: str,
        df: pd.DataFrame,
        source: str = 'mt5'
    ) -> int:
        """
        批量写入历史数据（拉取时使用）
        直接写入，不经过缓冲区
        """
        if df.empty:
            return 0

        df = df.copy()
        df['symbol']    = symbol
        df['timeframe'] = timeframe
        df['source']    = source

        # 标准化时间列
        if 'timestamp' not in df.columns and 'time' in df.columns:
            df = df.rename(columns={'time': 'timestamp'})
        df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)

        cols = ['symbol', 'timeframe', 'timestamp',
                'open', 'high', 'low', 'close', 'volume', 'source']
        df = df[[c for c in cols if c in df.columns]]

        with self._lock:
            self._wconn.execute("""
                INSERT OR REPLACE INTO ohlcv
                SELECT * FROM df
            """)

        return len(df)

    # ─────────────────────────────────────────────
    #  读取接口
    # ─────────────────────────────────────────────

    def _get_rconn(self):
        """读连接：只读模式，支持并发"""
        return duckdb.connect(self.db_path, read_only=True)

    def get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        include_current: bool = True
    ) -> pd.DataFrame:
        """
        查询热存储中的OHLCV数据
        可选择包含当前未完成K线
        """
        with self._get_rconn() as conn:
            # 基础查询
            base = """
                SELECT timestamp, open, high, low, close, volume, source
                FROM ohlcv
                WHERE symbol=? AND timeframe=?
            """
            params = [symbol, timeframe]

            if start:
                base += " AND timestamp >= ?"
                params.append(start)
            if end:
                base += " AND timestamp <= ?"
                params.append(end)

            df = conn.execute(base, params).df()

            if include_current:
                curr = conn.execute("""
                    SELECT timestamp, open, high, low, close, volume,
                           'realtime' as source
                    FROM current_bar
                    WHERE symbol=? AND timeframe=?
                      AND timestamp > COALESCE(
                          (SELECT MAX(timestamp) FROM ohlcv
                           WHERE symbol=? AND timeframe=?),
                          '1970-01-01'
                      )
                """, [symbol, timeframe, symbol, timeframe]).df()

                if not curr.empty:
                    df = pd.concat([df, curr], ignore_index=True)

        return df.sort_values('timestamp').reset_index(drop=True)

    def get_month_data(
        self,
        symbol: str,
        timeframe: str,
        year: int,
        month: int
    ) -> pd.DataFrame:
        """获取指定月份全部数据（用于归档）"""
        start = datetime(year, month, 1)
        if month == 12:
            end = datetime(year + 1, 1, 1)
        else:
            end = datetime(year, month + 1, 1)

        return self.get_ohlcv(
            symbol, timeframe, start, end,
            include_current=False
        )

    def get_latest_timestamp(
        self, symbol: str, timeframe: str
    ) -> Optional[datetime]:
        """获取最新数据时间（用于增量拉取）"""
        with self._get_rconn() as conn:
            row = conn.execute("""
                SELECT MAX(timestamp) as ts FROM ohlcv
                WHERE symbol=? AND timeframe=?
            """, [symbol, timeframe]).fetchone()
        if row and row[0]:
            return pd.Timestamp(row[0]).to_pydatetime()
        return None

    def get_month_bar_count(
        self, symbol: str, timeframe: str, year: int, month: int
    ) -> int:
        """统计指定月份的K线数量"""
        with self._get_rconn() as conn:
            row = conn.execute("""
                SELECT COUNT(*) FROM ohlcv
                WHERE symbol=? AND timeframe=?
                  AND year(timestamp)=? AND month(timestamp)=?
            """, [symbol, timeframe, year, month]).fetchone()
        return row[0] if row else 0

    def delete_month(
        self, symbol: str, timeframe: str, year: int, month: int
    ):
        """
        删除已归档的月份数据（释放空间）
        归档完成后调用
        """
        with self._lock:
            self._wconn.execute("""
                DELETE FROM ohlcv
                WHERE symbol=? AND timeframe=?
                  AND year(timestamp)=? AND month(timestamp)=?
            """, [symbol, timeframe, year, month])
        logger.info(f"Deleted hot data: {symbol}/{timeframe} {year}-{month:02d}")

    def get_data_summary(self, symbol: str, timeframe: str) -> dict:
        """数据概览，用于状态检查"""
        with self._get_rconn() as conn:
            row = conn.execute("""
                SELECT
                    COUNT(*)        as total_bars,
                    MIN(timestamp)  as first_bar,
                    MAX(timestamp)  as last_bar,
                    COUNT(DISTINCT strftime(timestamp, '%Y-%m')) as months
                FROM ohlcv
                WHERE symbol=? AND timeframe=?
            """, [symbol, timeframe]).fetchone()

        if row:
            return {
                "total_bars": row[0],
                "first_bar":  str(row[1]) if row[1] else None,
                "last_bar":   str(row[2]) if row[2] else None,
                "months":     row[3]
            }
        return {}
```

---

## 冷存储层

```python
# backend/database/cold_store.py
"""
Parquet 冷存储管理器
职责：管理已归档的月度 Parquet 文件
"""
import pyarrow as pa
import pyarrow.parquet as pq
import pandas as pd
import duckdb
from pathlib import Path
from datetime import datetime
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)

# 统一Arrow Schema，确保所有文件格式一致
OHLCV_SCHEMA = pa.schema([
    ('timestamp', pa.timestamp('ms', tz='UTC')),
    ('open',      pa.float64()),
    ('high',      pa.float64()),
    ('low',       pa.float64()),
    ('close',     pa.float64()),
    ('volume',    pa.float64()),
    ('source',    pa.string()),
])


class ColdStore:
    """
    Parquet冷存储管理器

    文件路径规则：
    data/market/parquet/{SYMBOL}/{TIMEFRAME}/{YYYY_MM}.parquet
    """

    def __init__(self, base_path: str = "data/market/parquet"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _file_path(
        self, symbol: str, timeframe: str, year: int, month: int
    ) -> Path:
        p = self.base_path / symbol / timeframe
        p.mkdir(parents=True, exist_ok=True)
        return p / f"{year:04d}_{month:02d}.parquet"

    # ─────────────────────────────────────────────
    #  写入
    # ─────────────────────────────────────────────

    def write_month(
        self,
        symbol: str,
        timeframe: str,
        year: int,
        month: int,
        df: pd.DataFrame,
        source: str = 'mt5'
    ) -> str:
        """
        将DataFrame写入Parquet文件
        返回文件路径
        幂等操作：重复写入会覆盖
        """
        if df.empty:
            raise ValueError(f"Empty DataFrame for {symbol}/{timeframe} {year}-{month:02d}")

        df = df.copy()
        df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
        df['source']    = source
        df = df.sort_values('timestamp').drop_duplicates('timestamp')

        # 确保列完整
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col not in df.columns:
                raise ValueError(f"Missing column: {col}")

        table = pa.Table.from_pandas(
            df[['timestamp', 'open', 'high', 'low', 'close', 'volume', 'source']],
            schema=OHLCV_SCHEMA,
            preserve_index=False
        )

        path = self._file_path(symbol, timeframe, year, month)

        pq.write_table(
            table,
            str(path),
            compression='snappy',
            row_group_size=50_000,
            write_statistics=True,        # 支持谓词下推
            use_dictionary=['source'],
        )

        logger.info(
            f"Written {len(df)} bars → {path.name} "
            f"({path.stat().st_size / 1024:.1f} KB)"
        )
        return str(path)

    # ─────────────────────────────────────────────
    #  读取
    # ─────────────────────────────────────────────

    def read_month(
        self,
        symbol: str,
        timeframe: str,
        year: int,
        month: int
    ) -> pd.DataFrame:
        """读取单月Parquet文件"""
        path = self._file_path(symbol, timeframe, year, month)
        if not path.exists():
            return pd.DataFrame()

        return pq.read_table(str(path)).to_pandas()

    def read_range(
        self,
        symbol: str,
        timeframe: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """
        跨月读取，自动选择相关文件
        使用DuckDB扫描，利用Parquet统计信息跳过无关RowGroup
        """
        tf_path = self.base_path / symbol / timeframe
        if not tf_path.exists():
            return pd.DataFrame()

        # 按时间范围筛选文件
        all_files = sorted(tf_path.glob("*.parquet"))
        if not all_files:
            return pd.DataFrame()

        selected = self._filter_files(all_files, start, end)
        if not selected:
            return pd.DataFrame()

        file_list = str([str(f) for f in selected])

        query = f"""
            SELECT timestamp, open, high, low, close, volume, source
            FROM read_parquet({file_list})
            WHERE 1=1
        """
        params = []
        if start:
            query += " AND timestamp >= ?"
            params.append(start)
        if end:
            query += " AND timestamp < ?"
            params.append(end)
        query += " ORDER BY timestamp ASC"

        with duckdb.connect() as conn:
            return conn.execute(query, params).df()

    def _filter_files(
        self,
        files: List[Path],
        start: Optional[datetime],
        end: Optional[datetime]
    ) -> List[Path]:
        """根据时间范围筛选Parquet文件"""
        result = []
        for f in files:
            # 文件名格式: YYYY_MM.parquet
            try:
                y, m = f.stem.split('_')
                file_year, file_month = int(y), int(m)
            except ValueError:
                continue

            # 文件覆盖范围
            file_start = datetime(file_year, file_month, 1)
            if file_month == 12:
                file_end = datetime(file_year + 1, 1, 1)
            else:
                file_end = datetime(file_year, file_month + 1, 1)

            # 范围相交检查
            if start and file_end <= start:
                continue
            if end and file_start >= end:
                continue

            result.append(f)
        return result

    # ─────────────────────────────────────────────
    #  状态检查
    # ─────────────────────────────────────────────

    def exists(
        self, symbol: str, timeframe: str, year: int, month: int
    ) -> bool:
        return self._file_path(symbol, timeframe, year, month).exists()

    def get_file_info(
        self, symbol: str, timeframe: str, year: int, month: int
    ) -> Optional[dict]:
        """获取Parquet文件元信息"""
        path = self._file_path(symbol, timeframe, year, month)
        if not path.exists():
            return None

        meta = pq.read_metadata(str(path))
        pq_schema = pq.read_schema(str(path))

        return {
            "path":       str(path),
            "size_kb":    round(path.stat().st_size / 1024, 1),
            "num_rows":   meta.num_rows,
            "num_groups": meta.num_row_groups,
            "created":    datetime.fromtimestamp(
                              path.stat().st_ctime
                          ).isoformat(),
        }

    def scan_all(
        self, symbol: str, timeframe: str
    ) -> List[dict]:
        """扫描所有Parquet文件，返回覆盖情况"""
        tf_path = self.base_path / symbol / timeframe
        if not tf_path.exists():
            return []

        result = []
        for f in sorted(tf_path.glob("*.parquet")):
            try:
                y, m = f.stem.split('_')
                info = self.get_file_info(symbol, timeframe, int(y), int(m))
                if info:
                    info['year']  = int(y)
                    info['month'] = int(m)
                    result.append(info)
            except Exception:
                continue
        return result
```

---

## 缺口检测与同步管理器（核心）

```python
# backend/sync/gap_detector.py
"""
数据缺口检测器
负责分析当前数据状态，生成需要补全的任务列表
"""
from datetime import datetime
from typing import List, NamedTuple
from ..database.meta_store import MetaStore, DataStatus, MonthlyDataBlock
import logging

logger = logging.getLogger(__name__)


class SyncTask(NamedTuple):
    symbol:     str
    timeframe:  str
    year:       int
    month:      int
    action:     str         # FETCH_FULL | FETCH_INCREMENTAL | ARCHIVE | REPAIR
    priority:   int         # 1=最高
    reason:     str


class GapDetector:
    """
    数据缺口检测器

    检测逻辑（按你的场景举例）：
    当前: 2025年5月中旬
    DuckDB中: 5月数据（HOT）
    Parquet中: 只有2025_03.parquet

    → 检测到缺失: 2025_04（需要从MT5拉取并归档）
    → 检测到: 2025_05 在DuckDB中，状态HOT，无需处理
    → 检测到: 2025_03 已COLD，无需处理
    """

    def __init__(self, meta_store: MetaStore):
        self.meta = meta_store

    def analyze(
        self,
        symbol: str,
        timeframe: str,
        history_months: int = 12    # 向前检查多少个月
    ) -> List[SyncTask]:
        """
        分析数据状态，返回需要执行的同步任务列表
        按优先级排序
        """
        tasks = []
        now = datetime.now()

        # 计算检查范围
        start_year, start_month = self._months_ago(
            now.year, now.month, history_months
        )

        # 获取该Symbol/TF的所有数据块状态
        all_blocks = {
            (b.year, b.month): b
            for b in self.meta.get_all_blocks(symbol, timeframe)
        }

        # 遍历每个月份，逐一分析
        y, m = start_year, start_month
        while (y, m) <= (now.year, now.month):
            block = all_blocks.get((y, m))
            is_current = (y == now.year and m == now.month)
            is_past = not is_current

            task = self._analyze_block(
                symbol, timeframe, y, m,
                block, is_current, is_past, now
            )
            if task:
                tasks.append(task)

            m += 1
            if m > 12:
                m, y = 1, y + 1

        # 按优先级排序（数字小=优先级高）
        tasks.sort(key=lambda t: (t.priority, t.year, t.month))

        if tasks:
            logger.info(
                f"Gap analysis for {symbol}/{timeframe}: "
                f"{len(tasks)} tasks found"
            )
            for t in tasks:
                logger.info(
                    f"  [{t.priority}] {t.year}-{t.month:02d} "
                    f"{t.action}: {t.reason}"
                )

        return tasks

    def _analyze_block(
        self,
        symbol: str, timeframe: str,
        year: int, month: int,
        block: MonthlyDataBlock,
        is_current: bool, is_past: bool,
        now: datetime
    ) -> SyncTask:
        """分析单个月份数据块，返回需要执行的任务（或None）"""

        ym = f"{year}-{month:02d}"

        # ── 情况1：数据块完全不存在 ──
        if block is None:
            if is_current:
                return SyncTask(
                    symbol, timeframe, year, month,
                    action="FETCH_FULL",
                    priority=1,
                    reason=f"{ym} 当月数据缺失，需要拉取"
                )
            else:
                return SyncTask(
                    symbol, timeframe, year, month,
                    action="FETCH_AND_ARCHIVE",
                    priority=2,
                    reason=f"{ym} 历史月数据完全缺失"
                )

        # ── 情况2：上次同步失败 ──
        if block.status == DataStatus.ERROR:
            return SyncTask(
                symbol, timeframe, year, month,
                action="REPAIR",
                priority=2,
                reason=f"{ym} 上次同步失败: {block.error_msg}"
            )

        # ── 情况3：正在同步中（可能是僵尸状态）──
        if block.status in (DataStatus.SYNCING, DataStatus.ARCHIVING):
            # 超过30分钟还在SYNCING，认为是僵尸
            if block.last_sync:
                last = datetime.fromisoformat(block.last_sync)
                if (now - last).seconds > 1800:
                    return SyncTask(
                        symbol, timeframe, year, month,
                        action="REPAIR",
                        priority=3,
                        reason=f"{ym} 同步状态僵死，重试"
                    )
            return None  # 正常同步中，跳过

        # ── 情况4：当月HOT数据，检查是否需要增量更新 ──
        if is_current and block.status == DataStatus.HOT:
            if block.last_bar:
                last_bar_dt = datetime.fromisoformat(block.last_bar)
                gap_minutes = (now - last_bar_dt).seconds // 60
                # 根据时间周期判断是否需要更新
                tf_minutes = self._timeframe_to_minutes(timeframe)
                if gap_minutes > tf_minutes * 2:
                    return SyncTask(
                        symbol, timeframe, year, month,
                        action="FETCH_INCREMENTAL",
                        priority=1,
                        reason=f"{ym} 当月数据缺口 {gap_minutes}分钟"
                    )
            return None  # 当月数据正常

        # ── 情况5：历史月COLD数据，正常状态 ──
        if is_past and block.status == DataStatus.COLD:
            # 检查完整度
            if block.completeness < 0.8:
                return SyncTask(
                    symbol, timeframe, year, month,
                    action="REPAIR",
                    priority=4,
                    reason=f"{ym} Parquet完整度低 {block.completeness:.0%}"
                )
            return None  # 正常

        # ── 情况6：历史月HOT数据，需要归档 ──
        if is_past and block.status == DataStatus.HOT:
            return SyncTask(
                symbol, timeframe, year, month,
                action="ARCHIVE",
                priority=3,
                reason=f"{ym} 历史数据在DuckDB中未归档"
            )

        return None

    def _months_ago(self, year: int, month: int, n: int) -> tuple:
        """计算N个月前的年月"""
        total = year * 12 + month - n
        return total // 12, total % 12 or 12

    def _timeframe_to_minutes(self, timeframe: str) -> int:
        mapping = {
            "M1": 1, "M5": 5, "M15": 15, "M30": 30,
            "H1": 60, "H4": 240, "D1": 1440, "W1": 10080
        }
        return mapping.get(timeframe, 60)
```

```python
# backend/sync/sync_manager.py
"""
同步总调度器
APP启动 / 图表打开 / 定时任务 都通过这里驱动
"""
import asyncio
from datetime import datetime
from typing import Optional, Callable
import logging

from ..database.meta_store import MetaStore, DataStatus
from ..database.hot_store import HotStore
from ..database.cold_store import ColdStore
from ..data_sources.mt5_source import MT5DataSource
from .gap_detector import GapDetector, SyncTask

logger = logging.getLogger(__name__)


class SyncManager:
    """
    同步调度器

    调用时机：
    1. APP启动       → startup_sync()
    2. 图表切换Symbol → on_symbol_open()
    3. 月末定时任务   → archive_completed_months()
    """

    def __init__(
        self,
        mt5: MT5DataSource,
        hot: HotStore,
        cold: ColdStore,
        meta: MetaStore,
    ):
        self.mt5  = mt5
        self.hot  = hot
        self.cold = cold
        self.meta = meta
        self.detector = GapDetector(meta)

        # 进度回调（用于前端进度条）
        self._progress_cb: Optional[Callable] = None
        # 并发限制
        self._semaphore = asyncio.Semaphore(3)

    def set_progress_callback(self, cb: Callable):
        self._progress_cb = cb

    async def _report(self, msg: str, progress: float = None):
        if self._progress_cb:
            await self._progress_cb({"message": msg, "progress": progress})
        logger.info(msg)

    # ─────────────────────────────────────────────
    #  公开接口
    # ─────────────────────────────────────────────

    async def on_symbol_open(
        self,
        symbol: str,
        timeframe: str,
        history_months: int = 3
    ):
        """
        图表打开时调用
        场景：用户选择 EURUSD H1
        → 检查并补全过去N个月的数据
        """
        await self._report(
            f"Checking data for {symbol}/{timeframe}..."
        )

        tasks = self.detector.analyze(symbol, timeframe, history_months)

        if not tasks:
            await self._report(f"{symbol}/{timeframe} data is up to date ✓")
            return

        await self._report(
            f"Found {len(tasks)} sync tasks for {symbol}/{timeframe}"
        )

        # 按优先级串行执行（避免MT5过载）
        for i, task in enumerate(tasks):
            progress = i / len(tasks)
            await self._report(
                f"[{i+1}/{len(tasks)}] {task.action} "
                f"{task.year}-{task.month:02d}: {task.reason}",
                progress
            )
            await self._execute_task(task)

        await self._report(f"{symbol}/{timeframe} sync complete ✓", 1.0)

    async def startup_sync(self, watched_symbols: list):
        """
        APP启动时的全局同步检查
        只检查用户关注的Symbol，不全量同步
        """
        await self._report("Starting up, checking data integrity...")

        all_tasks = []
        for symbol, timeframe in watched_symbols:
            tasks = self.detector.analyze(symbol, timeframe)
            all_tasks.extend(tasks)

        if not all_tasks:
            await self._report("All watched data is up to date ✓")
            return

        # 并发执行（受semaphore限制）
        await asyncio.gather(*[
            self._execute_with_semaphore(t)
            for t in all_tasks
        ])

    async def archive_completed_months(self):
        """
        月末归档任务
        将上个月的DuckDB数据归档为Parquet
        """
        now = datetime.now()
        # 归档上个月
        if now.month == 1:
            archive_year, archive_month = now.year - 1, 12
        else:
            archive_year, archive_month = now.year, now.month - 1

        await self._report(
            f"Archiving {archive_year}-{archive_month:02d}..."
        )

        # 查找所有HOT状态的历史月数据
        # (简化：实际应遍历所有symbol/timeframe)
        pass

    # ─────────────────────────────────────────────
    #  任务执行
    # ─────────────────────────────────────────────

    async def _execute_with_semaphore(self, task: SyncTask):
        async with self._semaphore:
            await self._execute_task(task)

    async def _execute_task(self, task: SyncTask):
        """根据任务类型分发执行"""
        dispatch = {
            "FETCH_FULL":          self._fetch_full,
            "FETCH_INCREMENTAL":   self._fetch_incremental,
            "FETCH_AND_ARCHIVE":   self._fetch_and_archive,
            "ARCHIVE":             self._archive,
            "REPAIR":              self._repair,
        }
        handler = dispatch.get(task.action)
        if handler:
            await handler(task)
        else:
            logger.warning(f"Unknown task action: {task.action}")

    async def _fetch_full(self, task: SyncTask):
        """
        全量拉取：用于当月首次加载
        从MT5拉取本月全部数据 → 写入DuckDB
        """
        log_id = self.meta.log_sync_start(
            task.symbol, task.timeframe,
            task.year, task.month, "FETCH_FULL"
        )
        self.meta.update_status(
            task.symbol, task.timeframe,
            task.year, task.month,
            DataStatus.SYNCING
        )
        try:
            start = datetime(task.year, task.month, 1)
            now = datetime.now()
            # 当月：拉到现在；历史月：拉到月末
            if task.year == now.year and task.month == now.month:
                end = now
            else:
                if task.month == 12:
                    end = datetime(task.year + 1, 1, 1)
                else:
                    end = datetime(task.year, task.month + 1, 1)

            df = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.mt5.get_historical_data(
                    task.symbol,
                    task.timeframe,
                    start=start,
                    end=end
                )
            )

            if df.empty:
                raise ValueError("MT5 returned empty data")

            count = self.hot.bulk_write(
                task.symbol, task.timeframe, df
            )

            # 更新元数据
            self.meta.update_status(
                task.symbol, task.timeframe,
                task.year, task.month,
                DataStatus.HOT,
                bar_count=count,
                first_bar=str(df['timestamp'].min()),
                last_bar=str(df['timestamp'].max()),
            )
            self.meta.log_sync_finish(log_id, count, "OK")
            logger.info(
                f"FETCH_FULL {task.symbol}/{task.timeframe} "
                f"{task.year}-{task.month:02d}: {count} bars"
            )

        except Exception as e:
            self.meta.update_status(
                task.symbol, task.timeframe,
                task.year, task.month,
                DataStatus.ERROR,
                error_msg=str(e)
            )
            self.meta.log_sync_finish(log_id, 0, "FAILED", str(e))
            logger.error(f"FETCH_FULL failed: {e}")

    async def _fetch_incremental(self, task: SyncTask):
        """
        增量拉取：从最新数据时间到现在
        """
        log_id = self.meta.log_sync_start(
            task.symbol, task.timeframe,
            task.year, task.month, "FETCH_INCREMENTAL"
        )
        try:
            # 获取当前最新时间
            latest = self.hot.get_latest_timestamp(
                task.symbol, task.timeframe
            )
            if not latest:
                # 退化为全量拉取
                await self._fetch_full(task)
                return

            df = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.mt5.get_historical_data(
                    task.symbol,
                    task.timeframe,
                    start=latest,
                    count=5000
                )
            )

            if df.empty:
                self.meta.log_sync_finish(log_id, 0, "OK", "No new data")
                return

            # 过滤掉已有数据（MT5会包含start时间点的K线）
            df = df[df['timestamp'] > pd.Timestamp(latest, tz='UTC')]

            count = self.hot.bulk_write(
                task.symbol, task.timeframe, df
            )

            # 更新last_bar
            self.meta.update_status(
                task.symbol, task.timeframe,
                task.year, task.month,
                DataStatus.HOT,
                bar_count=self.hot.get_month_bar_count(
                    task.symbol, task.timeframe,
                    task.year, task.month
                ),
                last_bar=str(df['timestamp'].max()),
            )
            self.meta.log_sync_finish(log_id, count, "OK")

        except Exception as e:
            self.meta.log_sync_finish(log_id, 0, "FAILED", str(e))
            logger.error(f"FETCH_INCREMENTAL failed: {e}")

    async def _fetch_and_archive(self, task: SyncTask):
        """
        拉取历史月数据并直接归档到Parquet
        跳过DuckDB，节省热存储空间
        """
        log_id = self.meta.log_sync_start(
            task.symbol, task.timeframe,
            task.year, task.month, "FETCH_AND_ARCHIVE"
        )
        self.meta.update_status(
            task.symbol, task.timeframe,
            task.year, task.month, DataStatus.SYNCING
        )
        try:
            start = datetime(task.year, task.month, 1)
            if task.month == 12:
                end = datetime(task.year + 1, 1, 1)
            else:
                end = datetime(task.year, task.month + 1, 1)

            df = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.mt5.get_historical_data(
                    task.symbol, task.timeframe,
                    start=start, end=end
                )
            )

            if df.empty:
                raise ValueError("MT5 returned empty data")

            # 直接写Parquet
            path = self.cold.write_month(
                task.symbol, task.timeframe,
                task.year, task.month, df
            )

            self.meta.update_status(
                task.symbol, task.timeframe,
                task.year, task.month,
                DataStatus.COLD,
                bar_count=len(df),
                first_bar=str(df['timestamp'].min()),
                last_bar=str(df['timestamp'].max()),
                parquet_path=path,
            )
            self.meta.log_sync_finish(log_id, len(df), "OK")

        except Exception as e:
            self.meta.update_status(
                task.symbol, task.timeframe,
                task.year, task.month,
                DataStatus.ERROR, error_msg=str(e)
            )
            self.meta.log_sync_finish(log_id, 0, "FAILED", str(e))
            logger.error(f"FETCH_AND_ARCHIVE failed: {e}")

    async def _archive(self, task: SyncTask):
        """
        归档：把DuckDB中的历史月数据写到Parquet，然后从DuckDB删除
        """
        log_id = self.meta.log_sync_start(
            task.symbol, task.timeframe,
            task.year, task.month, "ARCHIVE"
        )
        self.meta.update_status(
            task.symbol, task.timeframe,
            task.year, task.month, DataStatus.ARCHIVING
        )
        try:
            df = self.hot.get_month_data(
                task.symbol, task.timeframe,
                task.year, task.month
            )

            if df.empty:
                raise ValueError("No data in hot store to archive")

            path = self.cold.write_month(
                task.symbol, task.timeframe,
                task.year, task.month, df
            )

            # 验证Parquet写入正确
            verify = self.cold.read_month(
                task.symbol, task.timeframe,
                task.year, task.month
            )
            if len(verify) != len(df):
                raise ValueError(
                    f"Archive verification failed: "
                    f"wrote {len(df)}, read back {len(verify)}"
                )

            # 验证通过 → 删除DuckDB中的数据
            self.hot.delete_month(
                task.symbol, task.timeframe,
                task.year, task.month
            )

            self.meta.update_status(
                task.symbol, task.timeframe,
                task.year, task.month,
                DataStatus.COLD,
                bar_count=len(df),
                parquet_path=path,
            )
            self.meta.log_sync_finish(log_id, len(df), "OK")

        except Exception as e:
            # 归档失败，保持HOT状态，不删除DuckDB数据
            self.meta.update_status(
                task.symbol, task.timeframe,
                task.year, task.month,
                DataStatus.HOT, error_msg=str(e)
            )
            self.meta.log_sync_finish(log_id, 0, "FAILED", str(e))
            logger.error(f"ARCHIVE failed: {e}")

    async def _repair(self, task: SyncTask):
        """修复：重新拉取数据"""
        logger.info(
            f"Repairing {task.symbol}/{task.timeframe} "
            f"{task.year}-{task.month:02d}"
        )
        # 根据是否已有Parquet决定策略
        if self.cold.exists(
            task.symbol, task.timeframe, task.year, task.month
        ):
            await self._fetch_and_archive(task)
        else:
            await self._fetch_full(task)
```

---

## 统一查询门面

```python
# backend/database/unified_query.py
"""
统一查询门面
前端和AI Bot统一从这里查数据
自动合并 Parquet(冷) + DuckDB(热)
"""
import pandas as pd
import duckdb
from datetime import datetime
from typing import Optional
import logging

from .hot_store import HotStore
from .cold_store import ColdStore
from .meta_store import MetaStore, DataStatus

logger = logging.getLogger(__name__)


class UnifiedQuery:

    def __init__(
        self,
        hot: HotStore,
        cold: ColdStore,
        meta: MetaStore
    ):
        self.hot  = hot
        self.cold = cold
        self.meta = meta

    def query(
        self,
        symbol: str,
        timeframe: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 1000,
        include_current_bar: bool = True
    ) -> pd.DataFrame:
        """
        统一查询，自动合并冷热数据

        查询决策树：
        ┌─ 只在Parquet时间范围内 → 只读Parquet
        ├─ 只在DuckDB时间范围内 → 只读DuckDB
        └─ 跨越冷热边界      → 读Parquet + 读DuckDB → 合并
        """
        parts = []

        # 获取元数据，判断哪些月份在哪里
        cold_blocks = {
            (b.year, b.month) for b in self.meta.get_cold_months(symbol, timeframe)
        }

        has_cold = bool(cold_blocks)
        has_hot  = self.hot.get_latest_timestamp(symbol, timeframe) is not None

        # ── 读取冷数据 ──
        if has_cold:
            cold_df = self.cold.read_range(symbol, timeframe, start, end)
            if not cold_df.empty:
                parts.append(cold_df)

        # ── 读取热数据 ──
        if has_hot:
            # 确定热数据的起始时间（避免和冷数据重叠）
            hot_start = start
            if parts:
                # 从冷数据最后时间之后开始读热数据
                cold_latest = parts[-1]['timestamp'].max()
                if hot_start is None or cold_latest > hot_start:
                    hot_start = cold_latest

            hot_df = self.hot.get_ohlcv(
                symbol, timeframe,
                start=hot_start,
                end=end,
                include_current=include_current_bar
            )
            if not hot_df.empty:
                parts.append(hot_df)

        if not parts:
            return pd.DataFrame()

        # ── 合并 ──
        result = pd.concat(parts, ignore_index=True)
        result = (
            result
            .drop_duplicates('timestamp')
            .sort_values('timestamp')
            .reset_index(drop=True)
        )

        # ── limit（取最新N条）──
        if limit and len(result) > limit:
            result = result.tail(limit).reset_index(drop=True)

        return result

    def query_for_chart(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 1000
    ) -> list:
        """
        图表专用查询，返回lightweight-charts格式
        [{"time": unix_timestamp, "open": ..., ...}]
        """
        df = self.query(symbol, timeframe, limit=limit)

        if df.empty:
            return []

        df['time'] = pd.to_datetime(
            df['timestamp']
        ).astype('int64') // 1_000_000_000  # 转为Unix秒

        return df[['time', 'open', 'high', 'low', 'close', 'volume']]\
               .to_dict('records')

    def get_data_status(self, symbol: str, timeframe: str) -> dict:
        """
        返回该Symbol/TF的完整数据状态
        用于前端显示数据覆盖情况
        """
        all_blocks = self.meta.get_all_blocks(symbol, timeframe)
        cold_files = self.cold.scan_all(symbol, timeframe)
        hot_summary = self.hot.get_data_summary(symbol, timeframe)

        return {
            "symbol":     symbol,
            "timeframe":  timeframe,
            "blocks":     [
                {
                    "year":         b.year,
                    "month":        b.month,
                    "status":       b.status.value,
                    "bar_count":    b.bar_count,
                    "completeness": round(b.completeness, 3),
                    "first_bar":    b.first_bar,
                    "last_bar":     b.last_bar,
                }
                for b in all_blocks
            ],
            "cold_files": cold_files,
            "hot":        hot_summary,
        }
```

---

## 完整数据流向

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  用户打开图表 EURUSD/H1 (当前: 2025年5月中旬)

  GapDetector.analyze()
  ┌─────────────────────────────────────────────┐
  │ 检查范围: 2025-02 ~ 2025-05               │
  │                                             │
  │ 2025-02 → MetaStore: COLD ✓  (Parquet)    │
  │ 2025-03 → MetaStore: COLD ✓  (Parquet)    │
  │ 2025-04 → MetaStore: MISSING ✗            │
  │ 2025-05 → MetaStore: MISSING ✗            │
  └─────────────────────────────────────────────┘
           ↓ 生成任务
  Tasks:
  [P2] 2025-04: FETCH_AND_ARCHIVE (直接存Parquet)
  [P1] 2025-05: FETCH_FULL        (存DuckDB热存储)

           ↓ SyncManager执行
  MT5.get_historical_data(2025-04) → ColdStore.write_month()
  MT5.get_historical_data(2025-05) → HotStore.bulk_write()
  MetaStore更新状态

           ↓ 查询
  UnifiedQuery.query()
  ├── ColdStore.read_range(02~04) → Parquet DuckDB scan
  └── HotStore.get_ohlcv(05~now) → DuckDB query
           ↓ 合并返回前端

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  实时数据流 (ZMQ → DuckDB → WebSocket)

  MT5 EA
   │ ZMQ PUSH
   ▼
  ZMQListener
   ├─→ HotStore.update_current_bar()   (未关闭K线, 高频)
   └─→ HotStore.buffer_closed_bar()    (已关闭K线, 批量flush)
   └─→ MessageBus.publish()            (广播给前端/Bot)

  月末: Archiver
   └─→ HotStore.get_month_data()
   └─→ ColdStore.write_month()         (验证后)
   └─→ HotStore.delete_month()         (释放空间)
   └─→ MetaStore.update_status(COLD)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```