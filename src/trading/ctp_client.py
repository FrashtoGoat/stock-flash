"""OpenCTP CTP 交易客户端：连接仿真/7x24 环境，登录并下单（A 股股票）。"""

from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def stock_code_to_exchange_instrument(code: str) -> tuple[str, str]:
    """A 股代码 -> (ExchangeID, InstrumentID)。CTP 股票：上交所 SSE，深交所 SZSE。"""
    code = code.strip()
    if not code:
        return "SSE", ""
    # 6 开头 -> 上交所；0/3 开头 -> 深交所
    if code.startswith("6") or code.startswith("5"):
        return "SSE", code
    return "SZSE", code


@dataclass
class CTPOrderResult:
    """单笔报单结果（简化）"""
    success: bool
    order_ref: str
    message: str
    order_sys_id: str = ""


def _run_ctp_client(
    td_url: str,
    user_id: str,
    password: str,
    broker_id: str,
    app_id: str,
    auth_code: str,
    cmd_queue: queue.Queue,
    result_queue: queue.Queue,
    login_event: threading.Event,
    login_ok: list[bool],
    login_msg: list[str],
) -> None:
    """在独立线程中运行 CTP API：登录后从 cmd_queue 取指令（order/quit），结果放入 result_queue。
    连接 OpenCTP 必须用 openctp-tts（TTS 的 CTPAPI），用 openctp-ctp 会报 4097 断开。"""
    try:
        from openctp_tts import tdapi
    except ImportError as e:
        login_ok.append(False)
        login_msg.append(f"未安装 openctp-tts，连接 OpenCTP 需用 TTS 库: {e}")
        login_event.set()
        return

    req_id = [0]

    def next_request_id() -> int:
        req_id[0] += 1
        return req_id[0]

    class Spi(tdapi.CThostFtdcTraderSpi):
        def __init__(self, api: tdapi.CThostFtdcTraderApi) -> None:
            super().__init__()
            self._api = api
            self._order_results: dict[int, Optional[CTPOrderResult]] = {}

        def OnFrontConnected(self) -> None:
            logger.info("CTP 交易前置已连接，正在登录...")
            req = tdapi.CThostFtdcReqUserLoginField()
            req.BrokerID = broker_id
            req.UserID = user_id
            req.Password = password
            if app_id:
                req.AppID = app_id
            if auth_code:
                req.UserProductInfo = auth_code
            self._api.ReqUserLogin(req, next_request_id())

        def OnRspUserLogin(
            self,
            pRspUserLogin: tdapi.CThostFtdcRspUserLoginField,
            pRspInfo: tdapi.CThostFtdcRspInfoField,
            nRequestID: int,
            bIsLast: bool,
        ) -> None:
            if pRspInfo and pRspInfo.ErrorID != 0:
                msg = (pRspInfo.ErrorMsg or "").strip() or f"ErrorID={pRspInfo.ErrorID}"
                logger.warning("CTP 登录失败: %s", msg)
                login_ok.append(False)
                login_msg.append(msg)
            else:
                logger.info("CTP 登录成功 (FrontID=%s SessionID=%s)", getattr(pRspUserLogin, "FrontID", ""), getattr(pRspUserLogin, "SessionID", ""))
                login_ok.append(True)
                login_msg.append("")
            login_event.set()

        def OnFrontDisconnected(self, nReason: int) -> None:
            """前置断开时触发，常见 nReason：0=网络断开 4097=连接被拒或协议不匹配"""
            if not login_ok:  # 尚未收到登录结果则标记为失败，避免一直等待
                login_ok.append(False)
                login_msg.append(f"交易前置断开 nReason={nReason}，请检查网络与前置地址")
                login_event.set()
            logger.warning("CTP 交易前置已断开: nReason=%s", nReason)

        def _put_order_result(self, result: CTPOrderResult) -> None:
            if getattr(self, "_order_response_sent", False):
                return
            self._order_response_sent = True
            try:
                result_queue.put_nowait(result)
            except queue.Full:
                pass

        def OnRspOrderInsert(
            self,
            pInputOrder: tdapi.CThostFtdcInputOrderField,
            pRspInfo: tdapi.CThostFtdcRspInfoField,
            nRequestID: int,
            bIsLast: bool,
        ) -> None:
            if nRequestID in self._order_results:
                return
            if pRspInfo and pRspInfo.ErrorID != 0:
                msg = (pRspInfo.ErrorMsg or "").strip() or f"ErrorID={pRspInfo.ErrorID}"
                self._order_results[nRequestID] = CTPOrderResult(success=False, order_ref=pInputOrder.OrderRef if pInputOrder else "", message=msg)
            else:
                self._order_results[nRequestID] = CTPOrderResult(
                    success=True,
                    order_ref=pInputOrder.OrderRef if pInputOrder else "",
                    message="已报",
                    order_sys_id=getattr(pInputOrder, "OrderSysID", "") or "",
                )
            self._put_order_result(self._order_results[nRequestID])

        def OnErrRtnOrderInsert(
            self,
            pInputOrder: tdapi.CThostFtdcInputOrderField,
            pRspInfo: tdapi.CThostFtdcRspInfoField,
        ) -> None:
            """报单被柜台拒绝时触发，与 OnRspOrderInsert 二选一"""
            if pRspInfo and pRspInfo.ErrorID != 0:
                msg = (pRspInfo.ErrorMsg or "").strip() or f"ErrorID={pRspInfo.ErrorID}"
            else:
                msg = "报单拒绝"
            self._put_order_result(CTPOrderResult(
                success=False,
                order_ref=pInputOrder.OrderRef if pInputOrder else "",
                message=msg,
            ))

        def OnRtnOrder(
            self,
            pOrder: tdapi.CThostFtdcOrderField,
        ) -> None:
            # 可选：用 OrderSysID 等更新状态，此处仅打日志
            if pOrder:
                logger.debug("CTP 报单回报: OrderRef=%s OrderSysID=%s OrderStatus=%s",
                             getattr(pOrder, "OrderRef", ""), getattr(pOrder, "OrderSysID", ""), getattr(pOrder, "OrderStatus", ""))

    # flow 文件统一放到 result/flow_ctp/ 下，避免污染项目根目录
    project_root = Path(__file__).resolve().parent.parent.parent
    flow_dir = project_root / "result" / "flow_ctp"
    flow_dir.mkdir(parents=True, exist_ok=True)
    flow_path = str(flow_dir / ("flow_ctp_" + str(time.time_ns())))
    api = tdapi.CThostFtdcTraderApi.CreateFtdcTraderApi(flow_path)
    spi = Spi(api)
    api.RegisterSpi(spi)
    api.RegisterFront(td_url)
    api.Init()
    login_event.wait(timeout=15)
    if not login_ok:
        api.Release()
        return
    if not login_ok[0]:
        api.Release()
        return

    while True:
        try:
            cmd = cmd_queue.get(timeout=0.5)
        except queue.Empty:
            continue
        if cmd is None or (isinstance(cmd, tuple) and cmd[0] == "quit"):
            break
        if isinstance(cmd, tuple) and cmd[0] == "order":
            _, direction, exchange_id, instrument_id, price, volume = cmd
            req = tdapi.CThostFtdcInputOrderField()
            req.BrokerID = broker_id
            req.InvestorID = user_id
            req.ExchangeID = exchange_id
            req.InstrumentID = instrument_id
            req.OrderRef = str(int(time.time() * 1000) % 10000000)
            req.Direction = tdapi.THOST_FTDC_D_Buy if direction == "buy" else tdapi.THOST_FTDC_D_Sell
            req.OrderPriceType = tdapi.THOST_FTDC_OPT_LimitPrice
            req.LimitPrice = price
            req.VolumeTotalOriginal = int(volume)
            req.CombOffsetFlag = tdapi.THOST_FTDC_OF_Open
            req.CombHedgeFlag = tdapi.THOST_FTDC_HF_Speculation
            req.TimeCondition = tdapi.THOST_FTDC_TC_GFD
            req.VolumeCondition = tdapi.THOST_FTDC_VC_AV
            req.MinVolume = 1
            req.ContingentCondition = tdapi.THOST_FTDC_CC_Immediately
            req.ForceCloseReason = tdapi.THOST_FTDC_FCC_NotForceClose
            rid = next_request_id()
            spi._order_results[rid] = None
            spi._order_response_sent = False
            ret = api.ReqOrderInsert(req, rid)
            if ret != 0:
                result_queue.put_nowait(CTPOrderResult(success=False, order_ref=req.OrderRef, message=f"ReqOrderInsert 返回 {ret}"))
    api.Release()


class OpenCTPClient:
    """OpenCTP 客户端封装：支持登录与同步下单（在后台线程跑 CTP）。"""

    def __init__(
        self,
        td_url: str,
        user_id: str,
        password: str,
        broker_id: str = "9999",
        app_id: str = "",
        auth_code: str = "",
    ) -> None:
        self.td_url = td_url
        self.user_id = user_id
        self.password = password
        self.broker_id = broker_id
        self.app_id = app_id or ""
        self.auth_code = auth_code or ""
        self._thread: Optional[threading.Thread] = None
        self._cmd_queue: queue.Queue = queue.Queue()
        self._result_queue: queue.Queue = queue.Queue(maxsize=16)
        self._login_event = threading.Event()
        self._login_ok: list[bool] = []
        self._login_msg: list[str] = []
        self._started = False

    def start(self) -> bool:
        """启动 CTP 线程并等待登录结果。"""
        if self._started:
            return True
        self._login_ok.clear()
        self._login_msg.clear()
        self._login_event.clear()
        self._thread = threading.Thread(
            target=_run_ctp_client,
            args=(
                self.td_url,
                self.user_id,
                self.password,
                self.broker_id,
                self.app_id,
                self.auth_code,
                self._cmd_queue,
                self._result_queue,
                self._login_event,
                self._login_ok,
                self._login_msg,
            ),
            daemon=True,
        )
        self._thread.start()
        self._login_event.wait(timeout=15)
        if not self._login_ok:
            logger.warning("CTP 登录未就绪")
            return False
        if not self._login_ok[0]:
            logger.warning("CTP 登录失败: %s", self._login_msg[0] if self._login_msg else "未知")
            return False
        self._started = True
        return True

    def submit_order(self, direction: str, stock_code: str, price: float, amount_yuan: float) -> CTPOrderResult:
        """按金额近似换算成手数（100 股整数倍）后下单。direction: buy / sell。"""
        if not self._started:
            ok = self.start()
            if not ok:
                return CTPOrderResult(success=False, order_ref="", message="CTP 未登录")
        exchange_id, instrument_id = stock_code_to_exchange_instrument(stock_code)
        if not instrument_id:
            return CTPOrderResult(success=False, order_ref="", message="合约代码为空")
        if price <= 0:
            return CTPOrderResult(success=False, order_ref="", message="价格需大于 0")
        # 金额 -> 股数，A 股最小 100 股
        volume = max(100, int(amount_yuan / price / 100) * 100)
        try:
            self._cmd_queue.put(("order", direction, exchange_id, instrument_id, price, volume))
            return self._result_queue.get(timeout=20)
        except queue.Empty:
            return CTPOrderResult(success=False, order_ref="", message="等待报单回报超时")
        except Exception as e:
            return CTPOrderResult(success=False, order_ref="", message=str(e))

    def stop(self) -> None:
        """请求后台线程退出。"""
        try:
            self._cmd_queue.put(("quit",))
        except Exception:
            pass
        self._started = False
