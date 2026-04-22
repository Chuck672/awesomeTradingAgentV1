//+------------------------------------------------------------------+
//|                                       Session Volume Profile.mq5 |
//+------------------------------------------------------------------+
#property copyright "Session VP v5"
#property version   "5.10"
#property indicator_chart_window
#property indicator_buffers 0
#property indicator_plots   0

#include <Canvas\Canvas.mqh>

enum SESSION_TYPE { SESSION_SYDNEY=0, SESSION_ASIA=1, SESSION_EUROPE=2, SESSION_US=3 };
#define MAX_S 4
#define MAX_D 30

//+------------------------------------------------------------------+
//| 输入参数                                                          |
//+------------------------------------------------------------------+
input string            uniqueID = "SVP5";
input ENUM_TIMEFRAMES   tf0 = PERIOD_CURRENT;
input int               DaysToCalculate = 5;
input int               ProfilePrecision = 100;
input double            ValueAreaPercentage = 70.0;
input int               MaxProfileWidthPercent = 70;
input ENUM_APPLIED_VOLUME AppliedVolume = VOLUME_REAL;

input string            _s1 = "";                          // ─── 时区设置 ───
input bool              AutoGMTOffset = true;              // 自动检测Broker GMT偏移
input int               ManualGMTOffset = 2;               // 手动偏移(Auto关闭时使用)

input string            _s2 = "";                          // ─── 时段 GMT 小时 ───
input bool              DisplaySydney = true;              // 显示悉尼(仅周一开盘)
input int               SydneyStartGMT = 21;              // 悉尼开始(前日GMT)
input int               SydneyEndGMT = 0;                 // 悉尼结束(GMT)
input bool              DisplayAsia = true;                // 显示亚洲
input int               AsiaStartGMT = 0;                 // 亚洲开始
input int               AsiaEndGMT = 7;                   // 亚洲结束
input bool              DisplayEurope = true;              // 显示欧洲
input int               EuropeStartGMT = 7;               // 欧洲开始
input int               EuropeEndGMT = 12;                // 欧洲结束
input bool              DisplayUS = true;                  // 显示美国
input int               USStartGMT = 12;                  // 美国开始
input int               USEndGMT = 21;                    // 美国结束(周五收盘)

input string            _s3 = "";                          // ─── 显示选项 ───
input bool              DisplayPOC = true;
input bool              DisplayVA = true;
input bool              DisplayLabels = true;
input bool              DisplayGMTInfo = false;             // 显示经纪商GMT信息

input string            _s4 = "";                          // ─── 颜色样式 ───
input color             ColorPart1 = clrLightSlateGray;    // 时段前1/3
input color             ColorPart2 = clrIndianRed;         // 时段中1/3
input color             ColorPart3 = clrMediumSeaGreen;    // 时段后1/3
input color             ColorSydneyClr = clrDarkOrchid;    // 悉尼颜色
input uchar             ProfileTransparency = 50;
input color             ColorPOC = clrYellow;
input color             ColorVA = clrOrange;

//+------------------------------------------------------------------+
//| 数据结构                                                          |
//+------------------------------------------------------------------+
struct PLevel { double v1, v2, v3, t; };

struct SData {
    datetime     st, et;
    double       minP, maxP, step;
    double       maxV, poc, vah, val;
    int          prec;
    PLevel       lv[];
    SESSION_TYPE type;
    bool         ok;
};

//+------------------------------------------------------------------+
//| 全局变量                                                          |
//+------------------------------------------------------------------+
ENUM_TIMEFRAMES tf;
SData   g_d[MAX_S][MAX_D];
bool    g_v[MAX_S][MAX_D];
CCanvas C;
int     cW, cH;
double  cMn, cMx;
uint    a1, a2, a3, aS, aP, aV;
uint    ltk = 0;
int     g_off = -999;
int     g_cachedAutoOff = -999;
bool    g_show[MAX_S];
string  g_lbl[MAX_S];
bool    g_canvasOK = false;              // ★ 面板就绪标志

//+------------------------------------------------------------------+
//| Canvas 创建 / 重建（可安全重复调用）                                |
//+------------------------------------------------------------------+
void CreateCanvas()
{
    if(g_canvasOK)
        return;

    //--- 彻底清理残留 ---
    C.Destroy();
    ObjectDelete(0, uniqueID + "_C");

    //--- 创建画布 ---
    if(!C.CreateBitmapLabel(uniqueID + "_C", 0, 0, 100, 100,
          COLOR_FORMAT_ARGB_NORMALIZE))
    {
        Print("[SVP] Canvas creation deferred, err=", GetLastError());
        return;                          // 不终止，下次重试
    }

    ObjectSetInteger(0, uniqueID + "_C", OBJPROP_BACK, true);
    g_canvasOK = true;
}

//+------------------------------------------------------------------+
//| 初始化                                                            |
//+------------------------------------------------------------------+
int OnInit()
{
    tf = (tf0 == PERIOD_CURRENT) ? _Period : tf0;
    if(DaysToCalculate < 1 || DaysToCalculate > MAX_D)
    {
        Alert("DaysToCalculate must be 1-30");
        return INIT_FAILED;
    }

    for(int i = 0; i < MAX_S; i++)
        for(int j = 0; j < MAX_D; j++)
            g_v[i][j] = false;

    a1 = ColorToARGB(ColorPart1, ProfileTransparency);
    a2 = ColorToARGB(ColorPart2, ProfileTransparency);
    a3 = ColorToARGB(ColorPart3, ProfileTransparency);
    aS = ColorToARGB(ColorSydneyClr, ProfileTransparency);
    aP = ColorToARGB(ColorPOC, 255);
    aV = ColorToARGB(ColorVA, 200);

    g_show[0] = DisplaySydney;  g_lbl[0] = "SYD";
    g_show[1] = DisplayAsia;    g_lbl[1] = "ASIA";
    g_show[2] = DisplayEurope;  g_lbl[2] = "EU";
    g_show[3] = DisplayUS;      g_lbl[3] = "US";

    //--- ★ Canvas: 复用已有 或 重建 ---
    if(!g_canvasOK || ObjectFind(0, uniqueID + "_C") < 0)
    {
        g_canvasOK = false;
        CreateCanvas();
    }

    ltk = 0;                             // ★ 重置节流，确保首次立即执行
    UpdChart(true);
    CheckOffset();

    EventSetMillisecondTimer(1000);       // ★ 周期性重试 + 刷新

    return INIT_SUCCEEDED;               // ★ 始终成功
}

//+------------------------------------------------------------------+
//| 反初始化                                                          |
//+------------------------------------------------------------------+
void OnDeinit(const int r)
{
    //--- ★ 参数修改 / 周期切换：保留 Canvas，避免异步残留 ---
    if(r != REASON_PARAMETERS && r != REASON_CHARTCHANGE)
    {
        C.Destroy();
        ObjectDelete(0, uniqueID + "_C");
        g_canvasOK = false;
    }

    ObjectDelete(0, uniqueID + "_info");
    EventKillTimer();
    ChartRedraw();
}

//+------------------------------------------------------------------+
//| 计算入口                                                          |
//+------------------------------------------------------------------+
int OnCalculate(const int rt, const int pc, const datetime &time[],
    const double &open[], const double &high[], const double &low[],
    const double &close[], const long &tick_volume[], const long &volume[],
    const int &spread[])
{
    if(pc == 0)
        for(int i = 0; i < MAX_S; i++)
            for(int j = 0; j < MAX_D; j++)
                g_v[i][j] = false;

    uint now = GetTickCount();
    if(now - ltk < 500 && pc != 0) return rt;
    ltk = now;

    if(!g_canvasOK) CreateCanvas();      // ★ 延迟重试

    CheckOffset();
    CalcAll();
    UpdChart(false);
    Render();
    return rt;
}

//+------------------------------------------------------------------+
//| ★ 定时器 — 确保切换周期后能自动恢复渲染                            |
//+------------------------------------------------------------------+
void OnTimer()
{
    if(!g_canvasOK) CreateCanvas();       // Canvas 恢复

    uint now = GetTickCount();
    if(now - ltk < 800) return;           // 与 OnCalculate 协调
    ltk = now;

    CheckOffset();
    CalcAll();
    UpdChart(false);
    Render();
}

//+------------------------------------------------------------------+
void OnChartEvent(const int id, const long &lp, const double &dp, const string &sp)
{
    if(id == CHARTEVENT_CHART_CHANGE)
    {
        if(UpdChart(false)) Render();
    }
}

//+------------------------------------------------------------------+
//| GMT Offset 自动检测                                               |
//+------------------------------------------------------------------+
int GetOff()
{
    if(!AutoGMTOffset) return ManualGMTOffset;

    datetime server = TimeCurrent();
    datetime gmt    = TimeGMT();
    long diff = (long)(server - gmt);

    if(MathAbs(diff) < 86400)
    {
        int h = (int)MathRound((double)diff / 3600.0);
        if(h >= -12 && h <= 14)
        {
            g_cachedAutoOff = h;
            return h;
        }
    }
    return (g_cachedAutoOff != -999) ? g_cachedAutoOff : ManualGMTOffset;
}

//+------------------------------------------------------------------+
void CheckOffset()
{
    int cur = GetOff();
    if(cur != g_off)
    {
        g_off = cur;
        for(int i = 0; i < MAX_S; i++)
            for(int j = 0; j < MAX_D; j++)
                g_v[i][j] = false;
        ShowInfo();
        Print("GMT Offset: GMT", (g_off >= 0 ? "+" : ""), g_off,
              AutoGMTOffset ? " [Auto]" : " [Manual]");
    }
}

//+------------------------------------------------------------------+
void ShowInfo()
{
    string nm = uniqueID + "_info";

    //--- ★ 开关控制：关闭时删除标签并返回 ---
    if(!DisplayGMTInfo)
    {
        ObjectDelete(0, nm);
        return;
    }

    //--- 创建标签 ---
    if(ObjectFind(0, nm) < 0)
    {
        ObjectCreate(0, nm, OBJ_LABEL, 0, 0, 0);
        ObjectSetInteger(0, nm, OBJPROP_CORNER,    CORNER_RIGHT_UPPER);
        ObjectSetInteger(0, nm, OBJPROP_ANCHOR,    ANCHOR_RIGHT_UPPER);  // ★ 关键修复
        ObjectSetInteger(0, nm, OBJPROP_XDISTANCE, 80);                  // ★ 加大距离，避开价格标签
        ObjectSetInteger(0, nm, OBJPROP_YDISTANCE, 20);
        ObjectSetInteger(0, nm, OBJPROP_FONTSIZE,  9);
        ObjectSetString (0, nm, OBJPROP_FONT,      "Consolas");
    }

    //--- 更新文字 ---
    string sign = (g_off >= 0) ? "+" : "";
    string mode = AutoGMTOffset ? "Auto" : "Manual";
    ObjectSetString (0, nm, OBJPROP_TEXT,
        StringFormat("Broker GMT%s%d [%s]", sign, g_off, mode));
    ObjectSetInteger(0, nm, OBJPROP_COLOR,
        AutoGMTOffset ? clrLime : clrDodgerBlue);
}

//+------------------------------------------------------------------+
//| 时段时间计算                                                       |
//+------------------------------------------------------------------+
bool GetSTime(datetime day0, SESSION_TYPE stype, datetime &ts, datetime &te)
{
    MqlDateTime dt;
    TimeToStruct(day0, dt);
    int dow = dt.day_of_week;

    int off = g_off;
    int gmtStart = 0, gmtEnd = 0;
    int dayOffStart = 0, dayOffEnd = 0;

    switch(stype)
    {
        case SESSION_SYDNEY:
            if(dow != 1) return false;
            gmtStart    = SydneyStartGMT;
            gmtEnd      = SydneyEndGMT;
            dayOffStart = -1;
            dayOffEnd   = 0;
            break;

        case SESSION_ASIA:
            gmtStart = AsiaStartGMT;
            gmtEnd   = AsiaEndGMT;
            break;

        case SESSION_EUROPE:
            gmtStart = EuropeStartGMT;
            gmtEnd   = EuropeEndGMT;
            break;

        case SESSION_US:
            gmtStart = USStartGMT;
            if(dow >= 1 && dow <= 4)
            {
                gmtEnd    = AsiaStartGMT;
                dayOffEnd = 1;
            }
            else
            {
                gmtEnd = USEndGMT;
            }
            break;

        default:
            return false;
    }

    int bStart = gmtStart + off;
    int bEnd   = gmtEnd + off;

    while(bStart < 0)   { bStart += 24; dayOffStart--; }
    while(bStart >= 24) { bStart -= 24; dayOffStart++; }
    while(bEnd < 0)     { bEnd += 24;   dayOffEnd--;   }
    while(bEnd >= 24)   { bEnd -= 24;   dayOffEnd++;   }

    if(dayOffEnd < dayOffStart ||
       (dayOffEnd == dayOffStart && bEnd <= bStart))
        dayOffEnd = dayOffStart + 1;

    ts = day0 + (datetime)(dayOffStart * 86400 + bStart * 3600);
    te = day0 + (datetime)(dayOffEnd * 86400   + bEnd * 3600);

    return (te > ts);
}

//+------------------------------------------------------------------+
//| 计算所有时段                                                       |
//+------------------------------------------------------------------+
void CalcAll()
{
    datetime days[];
    int dc = CopyTime(_Symbol, PERIOD_D1, 0, DaysToCalculate + 3, days);
    if(dc <= 0) return;
    ArraySetAsSeries(days, true);

    datetime now = TimeCurrent();
    int validDay = 0;

    for(int r = 0; r < dc && validDay < DaysToCalculate; r++)
    {
        MqlDateTime ck;
        TimeToStruct(days[r], ck);
        if(ck.day_of_week == 0 || ck.day_of_week == 6)
            continue;

        for(int s = 0; s < MAX_S; s++)
        {
            if(!g_show[s]) continue;

            datetime tStart, tEnd;
            if(!GetSTime(days[r], (SESSION_TYPE)s, tStart, tEnd))
                continue;

            if(tStart > now) continue;

            bool developing = (now >= tStart && now <= tEnd);
            if(!g_v[s][validDay] || developing)
                g_v[s][validDay] = CalcSession(days[r], (SESSION_TYPE)s, validDay);
        }
        validDay++;
    }
}

//+------------------------------------------------------------------+
//| 计算单个时段VP                                                     |
//+------------------------------------------------------------------+
bool CalcSession(datetime day0, SESSION_TYPE stype, int di)
{
    int si = (int)stype;
    SData sd;
    sd.ok = false;
    sd.type = stype;

    if(!GetSTime(day0, stype, sd.st, sd.et)) return false;

    MqlRates rates[];
    int cnt = CopyRates(_Symbol, tf, sd.st, sd.et, rates);
    if(cnt <= 0) return false;

    sd.maxP = rates[0].high;
    sd.minP = rates[0].low;
    for(int i = 1; i < cnt; i++)
    {
        if(rates[i].high > sd.maxP) sd.maxP = rates[i].high;
        if(rates[i].low  < sd.minP) sd.minP = rates[i].low;
    }
    double range = sd.maxP - sd.minP;
    if(range <= 0) return false;

    sd.prec = ProfilePrecision;
    sd.step = range / sd.prec;
    if(sd.step <= 0) return false;

    ArrayResize(sd.lv, sd.prec);
    for(int i = 0; i < sd.prec; i++)
    {
        sd.lv[i].v1 = 0;
        sd.lv[i].v2 = 0;
        sd.lv[i].v3 = 0;
        sd.lv[i].t  = 0;
    }
    sd.maxV = 0;

    datetime seg = (sd.et - sd.st) / 3;
    datetime t1  = sd.st + seg;
    datetime t2  = sd.st + 2 * seg;
    double inv   = 1.0 / sd.step;

    for(int i = 0; i < cnt; i++)
    {
        long vol = (AppliedVolume == VOLUME_REAL && rates[i].real_volume > 0)
                   ? rates[i].real_volume : rates[i].tick_volume;
        if(vol <= 0) continue;

        int part = (rates[i].time >= t2) ? 3 : (rates[i].time >= t1) ? 2 : 1;

        int sL = (int)MathFloor((rates[i].low  - sd.minP) * inv);
        int eL = (int)MathFloor((rates[i].high - sd.minP) * inv);
        if(sL < 0) sL = 0;
        if(eL >= sd.prec) eL = sd.prec - 1;
        if(sL > eL) continue;

        double vpl = (double)vol / (eL - sL + 1);
        for(int lv = sL; lv <= eL; lv++)
        {
            if(part == 1)      sd.lv[lv].v1 += vpl;
            else if(part == 2) sd.lv[lv].v2 += vpl;
            else               sd.lv[lv].v3 += vpl;
            sd.lv[lv].t += vpl;
        }
    }

    int pocIdx = 0;
    for(int i = 0; i < sd.prec; i++)
    {
        if(sd.lv[i].t > sd.maxV)
        {
            sd.maxV = sd.lv[i].t;
            pocIdx = i;
        }
    }
    if(sd.maxV <= 0) return false;
    sd.poc = sd.minP + (pocIdx + 0.5) * sd.step;

    double totalVol = 0;
    for(int i = 0; i < sd.prec; i++) totalVol += sd.lv[i].t;
    double target = totalVol * ValueAreaPercentage / 100.0;
    double current = sd.lv[pocIdx].t;
    int ui = pocIdx, li = pocIdx;
    while(current < target && (ui < sd.prec - 1 || li > 0))
    {
        double uv  = (ui < sd.prec - 1) ? sd.lv[ui + 1].t : 0;
        double lv2 = (li > 0)           ? sd.lv[li - 1].t : 0;
        if(uv >= lv2 && ui < sd.prec - 1)
        {
            ui++;
            current += sd.lv[ui].t;
        }
        else if(li > 0)
        {
            li--;
            current += sd.lv[li].t;
        }
        else break;
    }
    sd.vah = sd.minP + (ui + 1) * sd.step;
    sd.val = sd.minP + li * sd.step;
    sd.ok  = true;

    CopySessionToGlobal(si, di, sd);
    return true;
}

//+------------------------------------------------------------------+
//| 将局部SData拷贝到全局数组                                          |
//+------------------------------------------------------------------+
void CopySessionToGlobal(int si, int di, SData &src)
{
    g_d[si][di].st   = src.st;
    g_d[si][di].et   = src.et;
    g_d[si][di].minP = src.minP;
    g_d[si][di].maxP = src.maxP;
    g_d[si][di].step = src.step;
    g_d[si][di].prec = src.prec;
    g_d[si][di].maxV = src.maxV;
    g_d[si][di].poc  = src.poc;
    g_d[si][di].vah  = src.vah;
    g_d[si][di].val  = src.val;
    g_d[si][di].type = src.type;
    g_d[si][di].ok   = src.ok;
    ArrayResize(g_d[si][di].lv, src.prec);
    ArrayCopy(g_d[si][di].lv, src.lv);
}

//+------------------------------------------------------------------+
//| 图表属性更新                                                       |
//+------------------------------------------------------------------+
bool UpdChart(bool force)
{
    int w     = (int)ChartGetInteger(0, CHART_WIDTH_IN_PIXELS);
    int h     = (int)ChartGetInteger(0, CHART_HEIGHT_IN_PIXELS);
    double mn = ChartGetDouble(0, CHART_PRICE_MIN);
    double mx = ChartGetDouble(0, CHART_PRICE_MAX);
    if(force || w != cW || h != cH || mn != cMn || mx != cMx)
    {
        cW = w; cH = h; cMn = mn; cMx = mx;
        if(cW > 0 && cH > 0 && g_canvasOK)  // ★ 增加 g_canvasOK 检查
            C.Resize(cW, cH);
        return true;
    }
    return false;
}

//+------------------------------------------------------------------+
int TtoX(datetime t)
{
    int s = iBarShift(_Symbol, _Period, t, false);
    if(s < 0) return -1;
    datetime rt = iTime(_Symbol, _Period, s);
    int x = 0, y = 0;
    return ChartTimePriceToXY(0, 0, rt, cMn, x, y) ? x : -1;
}

//+------------------------------------------------------------------+
int PtoY(double p)
{
    if(cMx <= cMn) return 0;
    return (int)MathRound((cMx - p) * cH / (cMx - cMn));
}

//+------------------------------------------------------------------+
//| 渲染                                                              |
//+------------------------------------------------------------------+
void Render()
{
    if(!g_canvasOK) return;              // ★ Canvas 未就绪时跳过
    if(cW <= 0 || cH <= 0) return;

    C.Erase(0);
    for(int d = 0; d < DaysToCalculate; d++)
        for(int s = 0; s < MAX_S; s++)
            if(g_show[s] && g_v[s][d])
                Draw(s, d);
    C.Update();
}

//+------------------------------------------------------------------+
//| 绘制单个时段                                                       |
//+------------------------------------------------------------------+
void Draw(int si, int di)
{
    if(!g_d[si][di].ok || g_d[si][di].maxV <= 0) return;

    datetime startT  = g_d[si][di].st;
    datetime endT    = g_d[si][di].et;
    double   minP    = g_d[si][di].minP;
    double   maxP    = g_d[si][di].maxP;
    double   step    = g_d[si][di].step;
    double   maxVol  = g_d[si][di].maxV;
    double   pocP    = g_d[si][di].poc;
    double   vahP    = g_d[si][di].vah;
    double   valP    = g_d[si][di].val;
    int      prec    = g_d[si][di].prec;
    SESSION_TYPE stp = g_d[si][di].type;

    int x0 = TtoX(startT), x1 = TtoX(endT);
    if(x0 == -1 && x1 == -1) return;
    if(x0 == -1) x0 = 0;
    if(x1 == -1) x1 = cW;
    if(x1 <= x0) x1 = x0 + 40;
    if(x1 < 0 || x0 > cW) return;

    int maxW = (int)((x1 - x0) * MaxProfileWidthPercent / 100.0);
    if(maxW < 5) maxW = 5;

    bool isSyd = (stp == SESSION_SYDNEY);
    uint c1 = isSyd ? aS : a1;
    uint c2 = isSyd ? aS : a2;
    uint c3 = isSyd ? aS : a3;

    for(int i = 0; i < prec; i++)
    {
        double tv = g_d[si][di].lv[i].t;
        if(tv <= 0) continue;

        int y1 = PtoY(minP + i * step);
        int y2 = PtoY(minP + (i + 1) * step);
        int yt = MathMin(y1, y2), yb = MathMax(y1, y2);
        if(yb == yt) yb = yt + 1;
        if(yb < 0 || yt > cH) continue;
        if(yt < 0) yt = 0;
        if(yb > cH) yb = cH;

        int w1 = (int)(g_d[si][di].lv[i].v1 / maxVol * maxW);
        int w2 = (int)(g_d[si][di].lv[i].v2 / maxVol * maxW);
        int w3 = (int)(g_d[si][di].lv[i].v3 / maxVol * maxW);
        int xc = x0;
        if(w1 > 0) { C.FillRectangle(xc, yt, xc + w1, yb, c1); xc += w1; }
        if(w2 > 0) { C.FillRectangle(xc, yt, xc + w2, yb, c2); xc += w2; }
        if(w3 > 0) { C.FillRectangle(xc, yt, xc + w3, yb, c3); }
    }

    int dx0 = MathMax(0, x0), dx1 = MathMin(cW, x1);
    if(DisplayPOC)
    {
        int py = PtoY(pocP);
        if(py >= 0 && py < cH)
            C.FillRectangle(dx0, py - 1, dx1, py + 1, aP);
    }

    if(DisplayVA)
    {
        int vy = PtoY(vahP), ly = PtoY(valP);
        for(int x = dx0; x < dx1; x += 6)
        {
            int xe = MathMin(x + 3, dx1);
            if(vy >= 0 && vy < cH) C.FillRectangle(x, vy, xe, vy + 1, aV);
            if(ly >= 0 && ly < cH) C.FillRectangle(x, ly, xe, ly + 1, aV);
        }
    }

    if(DisplayLabels)
    {
        int lx = MathMax(2, x0 + 3);
        int ly = PtoY(maxP) - 15;
        if(ly < 0) ly = 2;
        C.TextOut(lx, ly, g_lbl[si], ColorToARGB(clrWhite, 200), TA_LEFT);
    }
}
//+------------------------------------------------------------------+