//+------------------------------------------------------------------+
//| AiFxBridge.mq5  —  AI FX Trader file-based bridge               |
//| Communicates with Python via text files in Terminal Common/Files  |
//| No sockets required — works on all MT5 builds and platforms.     |
//| Attach to any chart.                                             |
//+------------------------------------------------------------------+
#property copyright "AI FX Trader"
#property version   "1.00"
#property strict

input int    InpMagic   = 20260101;       // Magic number (must match Python side)
input int    InpTimerMs = 50;             // Polling interval ms
input string InpReqFile = "aifx_req.txt"; // Request file name
input string InpResFile = "aifx_res.txt"; // Response file name

//--- Init / Deinit -----------------------------------------------------------

int OnInit()
{
   // Clean up stale files from a previous session
   if(FileIsExist(InpReqFile, FILE_COMMON)) FileDelete(InpReqFile, FILE_COMMON);
   if(FileIsExist(InpResFile, FILE_COMMON)) FileDelete(InpResFile, FILE_COMMON);

   EventSetMillisecondTimer(InpTimerMs);
   Print("AiFxBridge: ready — polling every ", InpTimerMs, "ms via Common/Files");
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   if(FileIsExist(InpReqFile, FILE_COMMON)) FileDelete(InpReqFile, FILE_COMMON);
   if(FileIsExist(InpResFile, FILE_COMMON)) FileDelete(InpResFile, FILE_COMMON);
}

//--- Main polling loop -------------------------------------------------------

void OnTimer()
{
   if(!FileIsExist(InpReqFile, FILE_COMMON)) return;

   // Read request
   int fh = FileOpen(InpReqFile, FILE_READ|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(fh == INVALID_HANDLE) return;
   string line = FileReadString(fh);
   FileClose(fh);

   // Write response BEFORE deleting the request file.
   // Python polls for the request file to disappear — that is the signal
   // that the response is fully written and safe to read.
   string response = Dispatch(line);

   int fw = FileOpen(InpResFile, FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(fw == INVALID_HANDLE)
   {
      Print("AiFxBridge: cannot write response file");
      return;
   }
   FileWriteString(fw, response + "\n");
   FileClose(fw);

   // Delete request file last — signals Python the response is ready
   FileDelete(InpReqFile, FILE_COMMON);
}

void OnTick() {}   // required placeholder

//--- String helpers ----------------------------------------------------------

int SplitStr(string s, string sep, string &parts[])
{
   ArrayResize(parts, 0);
   int count = 0;
   int start = 0;
   int slen  = StringLen(s);
   int dlen  = StringLen(sep);
   for(int i = 0; i <= slen - dlen; i++)
   {
      if(StringSubstr(s, i, dlen) == sep)
      {
         ArrayResize(parts, count + 1);
         parts[count++] = StringSubstr(s, start, i - start);
         start = i + dlen;
         i += dlen - 1;
      }
   }
   ArrayResize(parts, count + 1);
   parts[count++] = StringSubstr(s, start, slen - start);
   return count;
}

//--- Timeframe parser --------------------------------------------------------

ENUM_TIMEFRAMES ParseTF(string tf)
{
   if(tf == "M1")  return PERIOD_M1;
   if(tf == "M5")  return PERIOD_M5;
   if(tf == "M15") return PERIOD_M15;
   if(tf == "M30") return PERIOD_M30;
   if(tf == "H1")  return PERIOD_H1;
   if(tf == "H4")  return PERIOD_H4;
   if(tf == "D1")  return PERIOD_D1;
   if(tf == "W1")  return PERIOD_W1;
   if(tf == "MN1") return PERIOD_MN1;
   return PERIOD_H1;
}

//--- OHLCV serialiser --------------------------------------------------------

string RatesToString(MqlRates &rates[], int count)
{
   string r = "OK";
   for(int i = 0; i < count; i++)
   {
      r += "|" + IntegerToString((long)rates[i].time)
             + "," + DoubleToString(rates[i].open,  8)
             + "," + DoubleToString(rates[i].high,  8)
             + "," + DoubleToString(rates[i].low,   8)
             + "," + DoubleToString(rates[i].close, 8)
             + "," + IntegerToString(rates[i].tick_volume)
             + "," + IntegerToString(rates[i].spread);
   }
   return r;
}

//--- Deal send helper ---------------------------------------------------------

bool SendDealWithFillingFallback(MqlTradeRequest &req, MqlTradeResult &res)
{
   // Some brokers/symbols reject specific filling policies (retcode 10030).
   // Try common modes in sequence until one is accepted.
   ENUM_ORDER_TYPE_FILLING modes[3] = {
      ORDER_FILLING_FOK,
      ORDER_FILLING_IOC,
      ORDER_FILLING_RETURN
   };

   for(int i = 0; i < 3; i++)
   {
      req.type_filling = modes[i];
      ZeroMemory(res);
      if(OrderSend(req, res) && res.retcode == TRADE_RETCODE_DONE)
         return true;

      // 10030 = Unsupported filling mode. Retry next filling mode.
      if(res.retcode != 10030)
         return false;
   }

   return false;
}

//--- Command dispatcher ------------------------------------------------------

string Dispatch(string line)
{
   string parts[];
   int n = SplitStr(line, "|", parts);
   if(n == 0) return "ERR|empty command";
   string cmd = parts[0];

   //--- PING
   if(cmd == "PING") return "OK|PONG";

   //--- TICK|SYMBOL
   if(cmd == "TICK" && n >= 2)
   {
      MqlTick tick;
      if(!SymbolInfoTick(parts[1], tick)) return "ERR|Cannot get tick";
      return "OK|" + DoubleToString(tick.bid, 8)
               + "|" + DoubleToString(tick.ask, 8)
               + "|" + IntegerToString((long)tick.time);
   }

   //--- OHLCV|SYMBOL|TF|COUNT
   if(cmd == "OHLCV" && n >= 4)
   {
      MqlRates rates[];
      int count = CopyRates(parts[1], ParseTF(parts[2]), 0, (int)StringToInteger(parts[3]), rates);
      if(count <= 0) return "ERR|No data for " + parts[1];
      return RatesToString(rates, count);
   }

   //--- OHLCV_RANGE|SYMBOL|TF|FROM_TS|TO_TS
   if(cmd == "OHLCV_RANGE" && n >= 5)
   {
      datetime from = (datetime)StringToInteger(parts[3]);
      datetime to   = (datetime)StringToInteger(parts[4]);
      MqlRates rates[];
      int count = CopyRates(parts[1], ParseTF(parts[2]), from, to, rates);
      if(count <= 0) return "ERR|No data for range";
      return RatesToString(rates, count);
   }

   //--- SYMBOL_INFO|SYMBOL
   if(cmd == "SYMBOL_INFO" && n >= 2)
   {
      int    spread = (int)SymbolInfoInteger(parts[1], SYMBOL_SPREAD);
      double point  = SymbolInfoDouble(parts[1], SYMBOL_POINT);
      if(point == 0) return "ERR|Symbol not found";
      return "OK|" + IntegerToString(spread) + "|" + DoubleToString(point, 10);
   }

   //--- ACCOUNT
   if(cmd == "ACCOUNT")
   {
      double balance = AccountInfoDouble(ACCOUNT_BALANCE);
      double equity  = AccountInfoDouble(ACCOUNT_EQUITY);
      double free    = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
      return "OK|" + DoubleToString(balance, 2)
               + "|" + DoubleToString(equity, 2)
               + "|" + DoubleToString(free, 2);
   }

   //--- SYMBOLS
   if(cmd == "SYMBOLS")
   {
      string r = "OK";
      int total = SymbolsTotal(false);
      for(int i = 0; i < total; i++)
      {
         string name = SymbolName(i, false);
         if((bool)SymbolInfoInteger(name, SYMBOL_VISIBLE))
            r += "|" + name;
      }
      return r;
   }

   //--- POSITIONS
   if(cmd == "POSITIONS")
   {
      string r = "OK";
      for(int i = 0; i < PositionsTotal(); i++)
      {
         ulong ticket = PositionGetTicket(i);
         if(ticket == 0) continue;
         if(!PositionSelectByTicket(ticket)) continue;
         if((int)PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
         r += "|" + IntegerToString(ticket)
                + "," + PositionGetString(POSITION_SYMBOL)
                + "," + IntegerToString((int)PositionGetInteger(POSITION_TYPE))
                + "," + DoubleToString(PositionGetDouble(POSITION_VOLUME), 2)
                + "," + DoubleToString(PositionGetDouble(POSITION_PRICE_OPEN), 8)
                + "," + DoubleToString(PositionGetDouble(POSITION_SL), 8)
                + "," + DoubleToString(PositionGetDouble(POSITION_TP), 8)
                + "," + DoubleToString(PositionGetDouble(POSITION_PROFIT), 2)
                + "," + IntegerToString((long)PositionGetInteger(POSITION_TIME));
      }
      return r;
   }

   //--- HISTORY|DAYS
   if(cmd == "HISTORY" && n >= 2)
   {
      int days = (int)StringToInteger(parts[1]);
      datetime from = TimeCurrent() - (datetime)(days * 86400);
      if(!HistorySelect(from, TimeCurrent())) return "ERR|HistorySelect failed";
      string r = "OK";
      for(int i = 0; i < HistoryDealsTotal(); i++)
      {
         ulong ticket = HistoryDealGetTicket(i);
         if((int)HistoryDealGetInteger(ticket, DEAL_MAGIC) != InpMagic) continue;
         r += "|" + IntegerToString(ticket)
                + "," + IntegerToString(HistoryDealGetInteger(ticket, DEAL_ORDER))
                + "," + HistoryDealGetString(ticket, DEAL_SYMBOL)
                + "," + IntegerToString((int)HistoryDealGetInteger(ticket, DEAL_TYPE))
                + "," + DoubleToString(HistoryDealGetDouble(ticket, DEAL_VOLUME), 2)
                + "," + DoubleToString(HistoryDealGetDouble(ticket, DEAL_PRICE), 8)
                + "," + DoubleToString(HistoryDealGetDouble(ticket, DEAL_PROFIT), 2)
                + "," + IntegerToString((long)HistoryDealGetInteger(ticket, DEAL_TIME))
                + "," + HistoryDealGetString(ticket, DEAL_COMMENT);
      }
      return r;
   }

   //--- ORDER|SYMBOL|TYPE|VOLUME|PRICE|SL|TP|COMMENT
   if(cmd == "ORDER" && n >= 8)
   {
      MqlTradeRequest req = {};
      MqlTradeResult  res = {};
      req.action       = TRADE_ACTION_DEAL;
      req.symbol       = parts[1];
      req.type         = (parts[2] == "BUY") ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
      req.volume       = StringToDouble(parts[3]);
      req.price        = StringToDouble(parts[4]);
      req.sl           = StringToDouble(parts[5]);
      req.tp           = StringToDouble(parts[6]);
      req.comment      = parts[7];
      req.deviation    = 10;
      req.magic        = InpMagic;
      req.type_time    = ORDER_TIME_GTC;
      if(!SendDealWithFillingFallback(req, res))
         return "ERR|" + IntegerToString(res.retcode) + ":" + res.comment;
      return "OK|" + IntegerToString(res.order)
               + "|" + DoubleToString(res.price, 8)
               + "|" + DoubleToString(res.volume, 2);
   }

   //--- CLOSE|TICKET
   if(cmd == "CLOSE" && n >= 2)
   {
      ulong ticket = (ulong)StringToInteger(parts[1]);
      if(!PositionSelectByTicket(ticket)) return "ERR|Position not found";
      string symbol = PositionGetString(POSITION_SYMBOL);
      double volume  = PositionGetDouble(POSITION_VOLUME);
      int    ptype   = (int)PositionGetInteger(POSITION_TYPE);
      MqlTick tick;
      if(!SymbolInfoTick(symbol, tick)) return "ERR|Cannot get tick";
      MqlTradeRequest req = {};
      MqlTradeResult  res = {};
      req.action       = TRADE_ACTION_DEAL;
      req.position     = ticket;
      req.symbol       = symbol;
      req.volume       = volume;
      req.type         = (ptype == ORDER_TYPE_BUY) ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
      req.price        = (req.type == ORDER_TYPE_SELL) ? tick.bid : tick.ask;
      req.deviation    = 10;
      req.magic        = InpMagic;
      req.comment      = "aifx:close";
      req.type_time    = ORDER_TIME_GTC;
      if(!SendDealWithFillingFallback(req, res))
         return "ERR|" + IntegerToString(res.retcode) + ":" + res.comment;
      return "OK|" + DoubleToString(res.price, 8);
   }

   //--- MODIFY|TICKET|SL|TP
   if(cmd == "MODIFY" && n >= 4)
   {
      ulong ticket = (ulong)StringToInteger(parts[1]);
      if(!PositionSelectByTicket(ticket)) return "ERR|Position not found";
      MqlTradeRequest req = {};
      MqlTradeResult  res = {};
      req.action   = TRADE_ACTION_SLTP;
      req.position = ticket;
      req.sl       = StringToDouble(parts[2]);
      req.tp       = StringToDouble(parts[3]);
      if(!OrderSend(req, res) || res.retcode != TRADE_RETCODE_DONE)
         return "ERR|" + IntegerToString(res.retcode) + ":" + res.comment;
      return "OK";
   }

   //--- PENDING|SYMBOL|TYPE|VOLUME|PRICE|SL|TP|COMMENT
   //    TYPE: BUY_LIMIT | SELL_LIMIT | BUY_STOP | SELL_STOP
   if(cmd == "PENDING" && n >= 8)
   {
      MqlTradeRequest req = {};
      MqlTradeResult  res = {};
      req.action    = TRADE_ACTION_PENDING;
      req.symbol    = parts[1];
      req.volume    = StringToDouble(parts[3]);
      req.price     = StringToDouble(parts[4]);
      req.sl        = StringToDouble(parts[5]);
      req.tp        = StringToDouble(parts[6]);
      req.comment   = parts[7];
      req.magic     = InpMagic;
      req.type_time = ORDER_TIME_GTC;

      string otype = parts[2];
      if     (otype == "BUY_LIMIT")  req.type = ORDER_TYPE_BUY_LIMIT;
      else if(otype == "SELL_LIMIT") req.type = ORDER_TYPE_SELL_LIMIT;
      else if(otype == "BUY_STOP")   req.type = ORDER_TYPE_BUY_STOP;
      else if(otype == "SELL_STOP")  req.type = ORDER_TYPE_SELL_STOP;
      else return "ERR|Unknown pending order type: " + otype;

      ZeroMemory(res);
      if(!OrderSend(req, res) || res.retcode != TRADE_RETCODE_DONE)
         return "ERR|" + IntegerToString(res.retcode) + ":" + res.comment;
      return "OK|" + IntegerToString(res.order)
               + "|" + DoubleToString(req.price, 8)
               + "|" + DoubleToString(req.volume, 2);
   }

   //--- ORDERS  — return all pending (unfilled) orders placed by this EA
   if(cmd == "ORDERS")
   {
      string r = "OK";
      for(int i = 0; i < OrdersTotal(); i++)
      {
         ulong ticket = OrderGetTicket(i);
         if(ticket == 0) continue;
         if(!OrderSelect(ticket)) continue;
         if((int)OrderGetInteger(ORDER_MAGIC) != InpMagic) continue;
         r += "|" + IntegerToString(ticket)
                + "," + OrderGetString(ORDER_SYMBOL)
                + "," + IntegerToString((int)OrderGetInteger(ORDER_TYPE))
                + "," + DoubleToString(OrderGetDouble(ORDER_VOLUME_INITIAL), 2)
                + "," + DoubleToString(OrderGetDouble(ORDER_PRICE_OPEN), 8);
      }
      return r;
   }

   //--- CANCEL_PENDING|TICKET
   if(cmd == "CANCEL_PENDING" && n >= 2)
   {
      ulong ticket = (ulong)StringToInteger(parts[1]);
      MqlTradeRequest req = {};
      MqlTradeResult  res = {};
      req.action = TRADE_ACTION_REMOVE;
      req.order  = ticket;
      ZeroMemory(res);
      if(!OrderSend(req, res) || res.retcode != TRADE_RETCODE_DONE)
         return "ERR|" + IntegerToString(res.retcode) + ":" + res.comment;
      return "OK";
   }

   return "ERR|unknown command: " + cmd;
}
