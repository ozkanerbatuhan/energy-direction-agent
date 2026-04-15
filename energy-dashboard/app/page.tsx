"use client";

import { useEffect, useState, useRef } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  ReferenceLine
} from "recharts";
import { Activity, Clock, Zap, AlertTriangle, ShieldCheck, ArrowRightLeft, Database, Sparkles, PowerOff, BellRing, Calendar, Info } from "lucide-react";

type ReasonParts = {
  baseline_mw: number;
  momentum_mw: number;
  outage_mw: number;
};

type HourlyPrediction = {
  hour: string;
  is_forecast: boolean;
  forecast_delta_mw: number;
  realized_delta_mw: number | null;
  outage_mw: number;
  reasoning: string;
  reason_parts?: ReasonParts;
  forecast_direction: string;
  lep_mw: number | null;
  dpp_mw: number | null;
  plan_delta_mw: number | null;
};

type PredictionResponse = {
  historical_baselines_mw: Record<string, number>;
  hourly_predictions: HourlyPrediction[];
  calculated_at: string;
};

type ApiResult<T> = { data: T | null; error: string | null };

const formatTime = (isoString?: string) => {
  if (!isoString) return "--:--";
  try {
    const d = new Date(isoString);
    return d.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" });
  } catch {
    return isoString;
  }
};

const formatDateDay = (isoString?: string) => {
  if (!isoString) return "--";
  try {
    const d = new Date(isoString);
    return d.toLocaleDateString("tr-TR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch {
    return isoString;
  }
};

function OutageTable({ title, rawItems }: { title: string, rawItems: any[] }) {
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState<"date" | "mw">("date");
  const ITEMS_PER_PAGE = 15;

  const handleSortChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setSortBy(e.target.value as "date" | "mw");
    setPage(1); // Reset page on sort
  };

  const sortedItems = [...rawItems].sort((a, b) => {
    if (sortBy === "mw") {
      const pA = (a.hourlyLoadAvg || 0) + (a.effectedSubscribers || 0) / 1000;
      const pB = (b.hourlyLoadAvg || 0) + (b.effectedSubscribers || 0) / 1000;
      if (pB !== pA) return pB - pA;
    }
    // Default: By Date Descending
    const dateA = a.date ? new Date(a.date).getTime() : 0;
    const dateB = b.date ? new Date(b.date).getTime() : 0;
    return dateB - dateA;
  });

  const totalPages = Math.ceil(sortedItems.length / ITEMS_PER_PAGE);
  const paginatedItems = sortedItems.slice((page - 1) * ITEMS_PER_PAGE, page * ITEMS_PER_PAGE);

  return (
    <div className="bg-slate-900/50 border border-slate-800 rounded-xl overflow-hidden shadow-sm flex flex-col mb-6">
      <div className="px-4 py-4 border-b border-slate-800 bg-slate-900/80 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <PowerOff className="h-4 w-4 text-orange-400" />
          <span className="font-semibold text-slate-200 tracking-wide text-sm">{title} <span className="text-slate-500 font-normal">({rawItems.length})</span></span>
        </div>
        <div className="flex items-center gap-3">
          <select 
            value={sortBy} 
            onChange={handleSortChange}
            className="bg-slate-800 border border-slate-700 text-xs text-slate-300 rounded px-2 py-1 outline-none"
          >
            <option value="date">En Yeni (Yayın Tarihi)</option>
            <option value="mw">En Kritik (MW / Abone)</option>
          </select>
        </div>
      </div>

      <div className="flex-1 w-full overflow-x-auto">
        <table className="w-full text-xs text-left min-w-[900px]">
          <thead className="text-slate-400 bg-slate-900 border-b border-slate-800">
            <tr>
              <th className="px-4 py-3">İl / İlçe</th>
              <th className="px-4 py-3">Arıza Başlangıcı</th>
              <th className="px-4 py-3">Arıza Bitişi</th>
              <th className="px-4 py-3">Dağıtım Firması</th>
              <th className="px-4 py-3 max-w-xs">Sebep</th>
              <th className="px-4 py-3 text-right">Etkilenen Abone</th>
              <th className="px-4 py-3 text-right">Yük Kaybı (MW)</th>
            </tr>
          </thead>
          <tbody>
            {paginatedItems.length === 0 ? (
              <tr><td colSpan={7} className="text-center p-8 text-slate-500">Kesinti Bulunmamaktadır.</td></tr>
            ) : paginatedItems.map((r, i) => {
              const isCritical = (r.effectedSubscribers >= 1000) || (r.hourlyLoadAvg >= 10);
              return (
                <tr key={r.id || i} className={`border-b border-slate-800/40 hover:bg-slate-800/50 transition-colors ${isCritical ? 'bg-orange-500/5' : ''}`}>
                  <td className="px-4 py-3 text-slate-200">
                    <div className="font-medium text-slate-100">{r.province}</div>
                    <div className="text-slate-400 text-[10px] mt-0.5">{r.district}</div>
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    <div className="text-slate-300 font-medium">{formatTime(r.startTime)}</div>
                    <div className="text-[10px] text-slate-500 mt-0.5">{r.startTime ? new Date(r.startTime).toLocaleDateString('tr-TR') : '—'}</div>
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    <div className="text-slate-300 font-medium">{formatTime(r.endTime)}</div>
                    <div className="text-[10px] text-slate-500 mt-0.5">{r.endTime ? new Date(r.endTime).toLocaleDateString('tr-TR') : '—'}</div>
                  </td>
                  <td className="px-4 py-3 text-slate-500 text-[10px]">
                    {r.distributionCompanyName?.replace(/_/g, ' ')}
                  </td>
                  <td className="px-4 py-3 text-slate-400 max-w-xs" title={r.reason}>
                    <div className="line-clamp-2 leading-relaxed">{r.reason}</div>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className={`font-semibold ${r.effectedSubscribers > 0 ? 'text-orange-400' : 'text-slate-500'}`}>
                      {r.effectedSubscribers ? r.effectedSubscribers.toLocaleString('tr-TR') : '—'}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-right">
                    {r.hourlyLoadAvg > 0 ? (
                      <div>
                        <div className="font-bold text-rose-400">{r.hourlyLoadAvg} MW</div>
                        <div className="text-[10px] text-slate-500 mt-0.5">saatlik ort.</div>
                      </div>
                    ) : (
                      <span className="text-slate-600">—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="px-4 py-3 bg-slate-900/40 border-t border-slate-800 flex items-center justify-between text-xs">
          <span className="text-slate-500">Sayfa {page} / {totalPages}</span>
          <div className="flex items-center gap-2">
            <button 
              disabled={page === 1}
              onClick={() => setPage(p => p - 1)}
              className="px-3 py-1 bg-slate-800 hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed rounded text-slate-300 transition-colors"
            >Önceki</button>
            <button 
              disabled={page === totalPages}
              onClick={() => setPage(p => p + 1)}
              className="px-3 py-1 bg-slate-800 hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed rounded text-slate-300 transition-colors"
            >Sonraki</button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function Dashboard() {
  const [activeTab, setActiveTab] = useState<"prediction" | "raw">("prediction");
  const [rawSubTab, setRawSubTab] = useState<"volume" | "finance" | "outages">("volume");

  // Format YYYY-MM-DD
  const [selectedDate, setSelectedDate] = useState<string>(
    new Date().toISOString().substring(0, 10)
  );

  const [data, setData] = useState<PredictionResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [lep, setLep] = useState<ApiResult<any>>({ data: null, error: null });
  const [rtCons, setRtCons] = useState<ApiResult<any>>({ data: null, error: null });
  const [rtGen, setRtGen] = useState<ApiResult<any>>({ data: null, error: null });
  const [dpp, setDpp] = useState<ApiResult<any>>({ data: null, error: null });
  const [finance, setFinance] = useState<ApiResult<any>>({ data: null, error: null });
  const [outages, setOutages] = useState<ApiResult<any>>({ data: null, error: null });
  const [chartTab, setChartTab] = useState<"agent" | "plan">("agent");
  const [showChartInfo, setShowChartInfo] = useState(false);

  const notifiedRef = useRef<Set<number>>(new Set());
  const isInitialLoadRef = useRef(true);

  // Initialization: Ask for Notifications
  useEffect(() => {
    if ("Notification" in window && Notification.permission !== "granted") {
      Notification.requestPermission();
    }
  }, []);

  // Outage Notification Trigger
  useEffect(() => {
    if (!outages.data || outages.data.status === "waiting") return;
    
    const todayStr = new Date().toISOString().substring(0, 10);
    const isToday = selectedDate === todayStr;

    const planned = outages.data.planned?.items || [];
    const unplanned = outages.data.unplanned?.items || [];
    const allOutages = [...planned, ...unplanned];

    let newNotificationsCount = 0;
    
    allOutages.forEach((r: any) => {
      const effectSubs = r.effectedSubscribers || 0;
      const loadMw = r.hourlyLoadAvg || 0;
      const isBig = effectSubs >= 500 || loadMw >= 10;
      
      if (isBig && r.id && !notifiedRef.current.has(r.id)) {
        // Her halükarda ID'yi kaydet ki bir daha karşımıza çıkmasın
        notifiedRef.current.add(r.id);
        
        // Sadece günümüz seçiliyken VE sayfanın İLK devasa yüklemesinde değilsek bildirim at
        if (isToday && !isInitialLoadRef.current) {
          newNotificationsCount++;
          
          if ("Notification" in window && Notification.permission === "granted") {
            new Notification(`BÜYÜK KESİNTİ: ${r.province} / ${r.district}`, {
              body: `Etkilenen Abone: ${effectSubs} | Tahmini Yük Kaybı: ${loadMw} MW\nSebep: ${r.reason}`,
              icon: '/favicon.ico'
            });
          }
        }
      }
    });

    if (newNotificationsCount > 0) {
      console.log(`[Notification] ${newNotificationsCount} adet yeni kritik kesinti bildirimi gösterildi.`);
    }

    // İlk yükleme tamamlandı, bundan sonraki API yoklamalarında gelen yeni ID'ler bildirim atabilir
    isInitialLoadRef.current = false;
  }, [outages, selectedDate]);


  const fetchEndpoint = async (url: string) => {
    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error("API hatası: " + res.status);
      const json = await res.json();
      return { data: json, error: null };
    } catch (err: any) {
      return { data: null, error: err.message };
    }
  };

  const fetchData = async (forceRefresh = false) => {
    setLoading(true);
    setError("");

    let dateQuery = `?date=${selectedDate}`;
    if (forceRefresh === true) {
      dateQuery += "&refresh=true";
    }
    
    // Prediction First
    try {
      const predRes = await fetch("https://energy-direction-agent.onrender.com/api/v1/prediction" + dateQuery);
      if (!predRes.ok) throw new Error("Ana API (Prediction) isteği başarısız oldu.");
      const predJson = await predRes.json();
      if (predJson.error) throw new Error(predJson.error);
      setData(predJson);
    } catch (err: any) {
      setError(err.message || "Bağlantı hatası.");
      setData(null);
    }

    // Parallel Raw Data
    const [
      resLep, resRtCons, resRtGen, resDpp, resFin, resOut
    ] = await Promise.all([
      fetchEndpoint("https://energy-direction-agent.onrender.com/api/v1/raw-data/load_estimation" + dateQuery),
      fetchEndpoint("https://energy-direction-agent.onrender.com/api/v1/raw-data/realtime_consumption" + dateQuery),
      fetchEndpoint("https://energy-direction-agent.onrender.com/api/v1/raw-data/realtime_generation" + dateQuery),
      fetchEndpoint("https://energy-direction-agent.onrender.com/api/v1/raw-data/dpp" + dateQuery),
      fetchEndpoint("https://energy-direction-agent.onrender.com/api/v1/raw-data/finance" + dateQuery),
      fetchEndpoint("https://energy-direction-agent.onrender.com/api/v1/raw-data/outages" + dateQuery),
    ]);

    setLep(resLep);
    setRtCons(resRtCons);
    setRtGen(resRtGen);
    setDpp(resDpp);
    setFinance(resFin);
    setOutages(resOut);

    setLoading(false);
  };

  useEffect(() => {
    fetchData();
    // Only auto-poll if we are on today's date
    const todayStr = new Date().toISOString().substring(0, 10);
    if (selectedDate === todayStr) {
      const interval = setInterval(fetchData, 30000);
      return () => clearInterval(interval);
    }
  }, [selectedDate]);



  const extractHour = (isoString?: string) => {
    if (!isoString) return "--:--";
    if (isoString.includes("T")) return isoString.split("T")[1].substring(0, 5);
    return isoString.substring(0, 5);
  };

  if (!data && loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-slate-950 text-emerald-500">
        <div className="animate-pulse text-xl tracking-widest flex items-center gap-3">
          <Activity className="animate-spin" /> Veriler Derleniyor...
        </div>
      </div>
    );
  }

  const renderTableBlock = (title: string, dataObj: ApiResult<any>, columns: {header: string, dataKey: string, isTotal?: boolean}[], listProp = "items") => {
    if (dataObj.error) return <div className="bg-slate-900/50 border border-slate-800 rounded-xl overflow-hidden p-6 text-rose-400">{title} Verisi Alınamadı: {dataObj.error}</div>;
    if (dataObj.data?.status === "waiting" || dataObj.data?.error) {
      return <div className="bg-slate-900/50 border border-slate-800 rounded-xl overflow-hidden p-6 text-slate-400">{title}: {dataObj.data?.message || dataObj.data?.error || 'Bekleniyor...'}</div>;
    }
    const items = dataObj.data?.[listProp] || [];
    if (items.length === 0) return <div className="bg-slate-900/50 border border-slate-800 rounded-xl overflow-hidden p-6 text-slate-500">{title} sistemde yok.</div>;

    const displayItems = items.filter((r: any) => {
      const dtStr = r.date || r.time || r.hour;
      return dtStr && dtStr.startsWith(selectedDate);
    });
    return (
      <div className="bg-slate-900/50 border border-slate-800 rounded-xl overflow-hidden shadow-sm">
        <div className="px-4 py-3 border-b border-slate-800 bg-slate-900/80 flex items-center gap-2">
          <div className="h-2 w-2 rounded-full bg-emerald-400"></div>
          <span className="font-medium text-slate-200 text-sm tracking-wide">{title}</span>
        </div>
        <div className="max-h-[400px] overflow-y-auto custom-scrollbar">
          <table className="w-full text-xs text-left">
            <thead className="text-slate-400 sticky top-0 bg-slate-900 shadow-md">
              <tr>
                <th className="px-4 py-3">Saat</th>
                {columns.map((c, i) => <th key={i} className="px-4 py-3 text-right">{c.header}</th>)}
              </tr>
            </thead>
            <tbody>
              {displayItems.map((r: any, i: number) => {
                const hourObj = extractHour(r.date || r.time || r.hour);
                return (
                  <tr key={i} className="border-b border-slate-800/50 hover:bg-slate-800/50 transition-colors">
                    <td className="px-4 py-2.5 text-slate-300 font-medium">{hourObj}</td>
                    {columns.map((c, idx) => (
                      <td key={idx} className={`px-4 py-2.5 text-right font-semibold ${c.isTotal ? 'text-emerald-400' : 'text-slate-300 opacity-90'}`}>
                        {r[c.dataKey] !== undefined && r[c.dataKey] !== null ? Number(r[c.dataKey]).toLocaleString("tr-TR", {maximumFractionDigits: 2}) : "-"}
                      </td>
                    ))}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  const renderVolumeTab = () => (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 animate-in fade-in slide-in-from-bottom-2 duration-500">
      {renderTableBlock("Gerçekleşen Tüketim (MWh)", rtCons, [{header: 'Tüketim', dataKey: 'consumption', isTotal: true}])}
      {renderTableBlock("Gerçekleşen Üretim (MWh)", rtGen, [{header: 'Üretim', dataKey: 'total', isTotal: true}])}
      {renderTableBlock("Yük Tahmin Planı / LEP", lep, [{header: 'Tahmin (MWh)', dataKey: 'lep', isTotal: true}])}
      {renderTableBlock("Kesinleşmiş G.Ü.P / KGÜP", dpp, [{header: 'Plan (MWh)', dataKey: 'total', isTotal: true}])}
    </div>
  );

  const renderFinanceTab = () => {
    if (finance.error) return <div className="text-rose-400 p-4">Hata: {finance.error}</div>;
    const fin = finance.data;
    if (!fin || fin.status === "waiting" || fin.error) return <div className="text-slate-400 p-4">{fin?.error || "Bekleniyor..."}</div>;

    const renderFinNode = (title: string, list: any[], columns: any) => renderTableBlock(title, {data: {items: list}, error: null}, columns);

    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-6 animate-in fade-in slide-in-from-bottom-2 duration-500">
        {renderFinNode("K.PTF", fin.k_ptf?.items || [], [{header: 'Fiyat (₺)', dataKey: 'price', isTotal: true}])}
        {renderFinNode("SMF", fin.smf?.items || [], [{header: 'Fiyat (₺)', dataKey: 'price', isTotal: true}])}
        {renderFinNode("YAT", fin.yat?.items || [], [{header: 'Miktar (MWh)', dataKey: 'downRegulation', isTotal: true}])}
        {renderFinNode("YAL", fin.yal?.items || [], [{header: 'Miktar (MWh)', dataKey: 'upRegulation', isTotal: true}])}
        {renderFinNode("Yön", fin.system_direction?.items || [], [{header: 'Yön', dataKey: 'systemDirection', isTotal: true}])}
      </div>
    );
  };

  const renderOutagesTab = () => {
    if (outages.error) return <div className="text-rose-400 p-4">Hata: {outages.error}</div>;
    const outData = outages.data;
    if (!outData || outData.status === "waiting" || outData.error) return <div className="text-slate-400 p-4">{outData?.error || "Bekleniyor..."}</div>;

    const planned = outData.planned?.items || [];
    const unplanned = outData.unplanned?.items || [];

    return (
      <div className="flex flex-col animate-in fade-in slide-in-from-bottom-2 duration-500">
         <OutageTable title="Planlı Arıza ve Şebeke Çalışmaları" rawItems={planned} />
         <OutageTable title="Plansız Kesintiler" rawItems={unplanned} />
      </div>
    );
  };

  const renderRawDataTab = () => {
    return (
      <div className="space-y-6">
        <div className="flex gap-2">
          <button onClick={() => setRawSubTab("volume")} className={`px-4 py-2 text-xs font-semibold rounded-lg transition-colors border ${rawSubTab === "volume" ? "bg-slate-800 border-slate-700 text-slate-200 shadow-inner" : "bg-transparent border-transparent text-slate-500 hover:text-slate-300 hover:bg-slate-900/50"}`}>Fiziksel Hacimler</button>
          <button onClick={() => setRawSubTab("finance")} className={`px-4 py-2 text-xs font-semibold rounded-lg transition-colors border ${rawSubTab === "finance" ? "bg-slate-800 border-slate-700 text-slate-200 shadow-inner" : "bg-transparent border-transparent text-slate-500 hover:text-slate-300 hover:bg-slate-900/50"}`}>Finansal Veriler (DGP)</button>
          <button onClick={() => setRawSubTab("outages")} className={`px-4 py-2 text-xs font-semibold rounded-lg transition-colors border ${rawSubTab === "outages" ? "bg-slate-800 border-slate-700 text-slate-200 shadow-inner" : "bg-transparent border-transparent text-slate-500 hover:text-slate-300 hover:bg-slate-900/50"}`}>Kesintiler / Arızalar</button>
        </div>
        {rawSubTab === "volume" && renderVolumeTab()}
        {rawSubTab === "finance" && renderFinanceTab()}
        {rawSubTab === "outages" && renderOutagesTab()}
      </div>
    );
  };


  const chartInfoTexts: Record<string, string> = {
    agent: "Tarihsel profil (son 3 gün) + saatlik momentum + arıza etkisi kullanılarak hesaplanan AI tahmin modeli. Koyu barlar tahmin, soluk barlar gerçekleşen saatleri temsil eder.",
    plan: "EPİAŞ Yük Tahmin Planı (LEP) ile Kesinleşmiş Gün Öncesi Üretim Planı (DPP) arasındaki ham fark. Piyasanın AI katmanı olmadan teorik beklentisini gösterir."
  };

  const renderPredictionTab = () => {
    if (!data) return <div className="text-slate-500">Geçmişe ait tahmin verisi bulunamadı.</div>;

    return (
      <div className="space-y-6 animate-in fade-in slide-in-from-left-2 duration-500">
        {/* Compact Status Bar */}
        <div className="flex flex-wrap items-center gap-4 bg-slate-900/40 border border-slate-800 rounded-lg px-4 py-3">
          <div className="flex items-center gap-2 text-sm">
            <Clock className="w-4 h-4 text-slate-500" />
            <span className="text-slate-400">Son Hesaplama:</span>
            <span className="text-white font-medium">{formatTime(data.calculated_at)}</span>
          </div>
          <div className="w-px h-4 bg-slate-700 hidden sm:block" />
          <div className="flex items-center gap-2 text-sm">
            <ShieldCheck className="w-4 h-4 text-emerald-500" />
            <span className="text-emerald-400 font-medium">Veri Hazır</span>
            <span className="text-slate-500">— {selectedDate}</span>
          </div>
        </div>

        {/* CHART with inner tabs */}
        <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-6 pt-5">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between mb-6 gap-3">
            {/* Chart Tabs */}
            <div className="flex gap-1 bg-slate-950/50 p-1 rounded-lg border border-slate-800">
              <button
                onClick={() => setChartTab("agent")}
                className={`px-3 py-1.5 text-xs font-medium rounded-md transition-all ${chartTab === "agent" ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 shadow" : "text-slate-400 hover:text-slate-200"}`}
              >
                <div className="flex items-center gap-1.5"><Sparkles className="w-3 h-3" /> Agent Tahmini</div>
              </button>
              <button
                onClick={() => setChartTab("plan")}
                className={`px-3 py-1.5 text-xs font-medium rounded-md transition-all ${chartTab === "plan" ? "bg-indigo-500/20 text-indigo-400 border border-indigo-500/30 shadow" : "text-slate-400 hover:text-slate-200"}`}
              >
                <div className="flex items-center gap-1.5"><Database className="w-3 h-3" /> Ham Plan (LEP - DPP)</div>
              </button>
            </div>
            {/* Info button */}
            <div className="relative">
              <button
                onMouseEnter={() => setShowChartInfo(true)}
                onMouseLeave={() => setShowChartInfo(false)}
                className="text-slate-500 hover:text-slate-300 transition-colors p-1"
              >
                <Info className="w-4 h-4" />
              </button>
              {showChartInfo && (
                <div className="absolute right-0 top-8 z-50 bg-slate-900 border border-slate-700 rounded-lg p-3 shadow-2xl w-72 text-xs text-slate-300 leading-relaxed">
                  {chartInfoTexts[chartTab]}
                </div>
              )}
            </div>
          </div>

          {/* Chart */}
          <div className="h-[400px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.hourly_predictions} margin={{ top: 20, right: 30, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                <XAxis dataKey="hour" tickFormatter={extractHour} stroke="#475569" tick={{fill: '#94a3b8', fontSize: 12}} axisLine={{ stroke: '#334155' }}/>
                <YAxis stroke="#475569" tick={{fill: '#94a3b8', fontSize: 12}} axisLine={{ stroke: '#334155' }} tickFormatter={(val) => `${val} MW`}/>
                <Tooltip 
                  cursor={{fill: '#1e293b', opacity: 0.4}}
                  content={({ active, payload }) => {
                    if (active && payload && payload.length) {
                      const hourData = payload[0].payload as HourlyPrediction;
                      const val = chartTab === "agent" ? hourData.forecast_delta_mw : hourData.plan_delta_mw;
                      const isDeficit = (val || 0) > 0;
                      return (
                        <div className="bg-slate-900 border border-slate-700 p-4 rounded-lg shadow-2xl max-w-xs">
                          <div className="font-bold text-lg text-white mb-2">{extractHour(hourData.hour)}</div>
                          {chartTab === "agent" ? (
                            <>
                              <div className={`text-xl font-bold mb-2 ${isDeficit ? 'text-rose-400' : 'text-emerald-400'}`}>
                                {hourData.forecast_delta_mw} MW <span className="text-sm font-normal">({hourData.forecast_direction})</span>
                              </div>
                              {!hourData.is_forecast && hourData.realized_delta_mw !== null && (
                                <div className="mt-1 pt-1 border-t border-slate-700 text-sm">
                                   Gerçekleşen: <span className="font-bold text-white">{hourData.realized_delta_mw} MW</span>
                                </div>
                              )}
                            </>
                          ) : (
                            <>
                              <div className={`text-xl font-bold mb-2 ${isDeficit ? 'text-rose-400' : 'text-emerald-400'}`}>
                                {hourData.plan_delta_mw ?? '—'} MW
                              </div>
                              <div className="text-xs text-slate-400 space-y-1 mt-1">
                                <p>LEP (Yük Tahmini): <span className="text-slate-200">{hourData.lep_mw ?? '—'} MW</span></p>
                                <p>DPP (Üretim Planı): <span className="text-slate-200">{hourData.dpp_mw ?? '—'} MW</span></p>
                              </div>
                            </>
                          )}
                          <div className="text-xs text-slate-300 border-t border-slate-700 pt-2 mt-2 italic">{hourData.reasoning}</div>
                        </div>
                      );
                    }
                    return null;
                  }}
                />
                <ReferenceLine y={0} stroke="#475569" />
                <Bar dataKey={chartTab === "agent" ? "forecast_delta_mw" : "plan_delta_mw"} radius={[4, 4, 0, 0]}>
                  {data.hourly_predictions.map((entry, index) => {
                    const val = chartTab === "agent" ? entry.forecast_delta_mw : (entry.plan_delta_mw ?? 0);
                    return (
                      <Cell key={`cell-${index}`} fill={val > 0 ? "#f43f5e" : "#10b981"} fillOpacity={entry.is_forecast ? 1 : 0.5}/>
                    );
                  })}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* TABLE — synced with chart tab */}
        <div className="bg-slate-900/50 border border-slate-800 rounded-xl overflow-hidden">
          <div className="p-6 border-b border-slate-800 flex justify-between items-center">
            <h2 className="text-lg font-medium text-white">
              {chartTab === "agent" ? "Akıllı Tahmin İzleme Modülü" : "EPİAŞ Ham Plan Verileri"}
            </h2>
          </div>
          <div className="overflow-x-auto custom-scrollbar">
            {chartTab === "agent" ? (
              <table className="w-full text-sm text-left">
                <thead className="text-xs text-slate-400 bg-slate-900 uppercase border-b border-slate-800 hidden md:table-header-group">
                  <tr>
                    <th className="px-6 py-4 w-[10%]">Saat</th>
                    <th className="px-6 py-4 w-[15%]">Durum</th>
                    <th className="px-6 py-4 w-[25%]">Yön & Sapma Tahmini</th>
                    <th className="px-6 py-4 w-[50%]">Gerekçe / Reasoning</th>
                  </tr>
                </thead>
                <tbody>
                  {data.hourly_predictions.map((row, idx) => {
                    const isDeficit = row.forecast_delta_mw > 0;
                    const isRealizedDeficit = row.realized_delta_mw !== null && row.realized_delta_mw > 0;
                    return (
                      <tr key={idx} className={`flex flex-col flex-no-wrap md:table-row mb-4 md:mb-0 border-b border-slate-800/50 hover:bg-slate-800/30 transition-colors ${row.is_forecast ? 'bg-slate-900/20' : 'bg-transparent opacity-80'}`}>
                        <td className="px-6 py-4 font-medium text-white whitespace-nowrap">{extractHour(row.hour)}</td>
                        <td className="px-6 py-4">
                          {row.is_forecast ? (
                            <div className="bg-indigo-500/20 text-indigo-400 p-2 rounded-full border border-indigo-500/20 w-fit" title="Tahmin Aşamasında">
                              <Sparkles className="w-4 h-4"/>
                            </div>
                          ) : (
                            <span className={`px-2 py-1 rounded text-[11px] font-bold tracking-wider w-fit block border ${isRealizedDeficit ? 'bg-rose-500/10 text-rose-400 border-rose-500/20' : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'}`}>
                              GERÇEKLEŞEN: {isRealizedDeficit ? 'AÇIK' : 'FAZLA'}
                            </span>
                          )}
                        </td>
                        <td className="px-6 py-4">
                          {row.is_forecast ? (
                            <>
                              <div className={`font-bold ${isDeficit ? 'text-rose-400' : 'text-emerald-400'}`}>{row.forecast_delta_mw} MW</div>
                              <div className="text-[10px] opacity-70 mt-1">{row.forecast_direction}</div>
                            </>
                          ) : (
                            <div className="flex flex-col gap-1.5 text-xs bg-slate-950/40 p-2 rounded border border-slate-800/80 max-w-[200px]">
                              <div className="flex justify-between items-center">
                                <span className="text-slate-500">Tahmin:</span>
                                <span className="font-semibold text-slate-300">{row.forecast_delta_mw} MW</span>
                              </div>
                              <div className="flex justify-between items-center">
                                <span className="text-slate-500">Gerçek:</span>
                                <span className="font-semibold text-white">{row.realized_delta_mw} MW</span>
                              </div>
                              <div className="flex justify-between items-center border-t border-slate-800/50 pt-1.5 mt-0.5">
                                <span className="text-slate-500">Fark:</span>
                                <span className="font-mono text-emerald-400">{Math.abs(Number(row.realized_delta_mw) - row.forecast_delta_mw).toFixed(2)} MW</span>
                              </div>
                            </div>
                          )}
                        </td>
                        <td className="px-6 py-4 text-xs">
                          {row.reason_parts ? (
                            <div className="flex flex-col gap-1.5">
                              <div className="flex items-center gap-2">
                                <span className="w-2 h-2 rounded-full bg-blue-500 shrink-0"></span>
                                <span className="text-slate-500 w-24 shrink-0">Tarihsel:</span>
                                <span className={`font-mono font-semibold ${row.reason_parts.baseline_mw > 0 ? 'text-rose-400' : row.reason_parts.baseline_mw < 0 ? 'text-emerald-400' : 'text-slate-400'}`}>
                                  {row.reason_parts.baseline_mw > 0 ? '+' : ''}{row.reason_parts.baseline_mw} MW
                                </span>
                              </div>
                              <div className="flex items-center gap-2">
                                <span className="w-2 h-2 rounded-full bg-amber-500 shrink-0"></span>
                                <span className="text-slate-500 w-24 shrink-0">Momentum:</span>
                                <span className={`font-mono font-semibold ${row.reason_parts.momentum_mw > 0 ? 'text-rose-400' : row.reason_parts.momentum_mw < 0 ? 'text-emerald-400' : 'text-slate-400'}`}>
                                  {row.reason_parts.momentum_mw > 0 ? '+' : ''}{row.reason_parts.momentum_mw} MW
                                </span>
                              </div>
                              <div className="flex items-center gap-2">
                                <span className="w-2 h-2 rounded-full bg-orange-500 shrink-0"></span>
                                <span className="text-slate-500 w-24 shrink-0">Arıza:</span>
                                <span className={`font-mono font-semibold ${row.reason_parts.outage_mw > 0 ? 'text-orange-400' : 'text-slate-400'}`}>
                                  +{row.reason_parts.outage_mw} MW
                                </span>
                              </div>
                            </div>
                          ) : (
                            <div className="text-slate-400 italic">{row.reasoning}</div>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            ) : (
              /* HAM PLAN TAB TABLE */
              <table className="w-full text-sm text-left">
                <thead className="text-xs text-slate-400 bg-slate-900 uppercase border-b border-slate-800 hidden md:table-header-group">
                  <tr>
                    <th className="px-6 py-4">Saat</th>
                    <th className="px-6 py-4">Yük Tahmini (LEP)</th>
                    <th className="px-6 py-4">Üretim Planı (DPP)</th>
                    <th className="px-6 py-4">Teorik Fark (LEP − DPP)</th>
                    <th className="px-6 py-4">Yön</th>
                  </tr>
                </thead>
                <tbody>
                  {data.hourly_predictions.map((row, idx) => {
                    const planDelta = row.plan_delta_mw;
                    const isDeficit = (planDelta ?? 0) > 0;
                    return (
                      <tr key={idx} className="border-b border-slate-800/50 hover:bg-slate-800/30 transition-colors">
                        <td className="px-6 py-4 font-medium text-white">{extractHour(row.hour)}</td>
                        <td className="px-6 py-4 text-slate-300">{row.lep_mw !== null ? `${row.lep_mw} MW` : '—'}</td>
                        <td className="px-6 py-4 text-slate-300">{row.dpp_mw !== null ? `${row.dpp_mw} MW` : '—'}</td>
                        <td className="px-6 py-4">
                          <span className={`font-bold ${isDeficit ? 'text-rose-400' : 'text-emerald-400'}`}>
                            {planDelta !== null ? `${planDelta} MW` : '—'}
                          </span>
                        </td>
                        <td className="px-6 py-4">
                          <span className={`text-[11px] font-semibold ${isDeficit ? 'text-rose-400' : 'text-emerald-400'}`}>
                            {planDelta !== null ? (isDeficit ? 'AÇIK' : 'FAZLA') : '—'}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-[#0B0F19] text-slate-300 p-4 md:p-8 font-sans selection:bg-emerald-500/30">
      <div className="max-w-[1600px] mx-auto space-y-6">
        
        {/* HEADER */}
        <header className="flex flex-col md:flex-row items-start md:items-center justify-between border-b border-slate-800 pb-6 gap-4">
          <div>
            <h1 className="text-3xl font-bold text-white flex items-center gap-3">
              <Zap className="text-emerald-500 h-8 w-8" />
              Energy Agent <span className="text-slate-500 font-light text-xl hidden sm:inline">| Akıllı Sistem Yönü Temsilcisi</span>
            </h1>
            <p className="text-slate-500 mt-1 text-sm">Zaman yolculuğu destekli Şeffaflık Platformu Analiz Paneli</p>
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            {/* Global Date Picker */}
            <div className="flex items-center gap-2">
              <button
                onClick={() => setSelectedDate(new Date().toISOString().substring(0, 10))}
                className="text-xs font-medium px-3 py-2 bg-slate-800/50 hover:bg-slate-700 text-slate-300 rounded-lg transition-colors border border-slate-700 hover:border-slate-600"
              >
                Bugün
              </button>
              <div className="flex items-center bg-slate-900 border border-slate-700 rounded-lg overflow-hidden group">
                <div className="pl-3 py-2 text-slate-400 group-hover:text-emerald-400 transition-colors">
                  <Calendar className="w-4 h-4" />
                </div>
                <input 
                  type="date"
                  value={selectedDate}
                  min={new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString().substring(0, 10)}
                  max={new Date().toISOString().substring(0, 10)}
                  onChange={(e) => setSelectedDate(e.target.value)}
                  className="bg-transparent text-sm text-slate-200 outline-none px-3 py-2 cursor-pointer [&::-webkit-calendar-picker-indicator]:opacity-50 [&::-webkit-calendar-picker-indicator]:hover:opacity-100"
                />
              </div>
            </div>
            
            <button 
              onClick={() => fetchData(true)}
              disabled={loading}
              className={`flex items-center gap-2 border border-slate-700 px-4 py-2 rounded-lg transition-colors text-sm font-medium ${loading ? 'opacity-50 bg-slate-900 cursor-not-allowed' : 'bg-slate-800 hover:bg-slate-700 hover:text-white'}`}
            >
              <Activity className={`w-4 h-4 ${loading ? 'animate-spin text-slate-400' : 'text-emerald-400'}`} /> {loading ? 'Getiriliyor...' : 'Yenile'}
            </button>
          </div>
        </header>

        {error && (
          <div className="bg-rose-500/10 border border-rose-500/20 text-rose-400 p-4 rounded-xl flex items-center gap-3">
            <AlertTriangle className="h-5 w-5 flex-shrink-0" />
            <p>{error}</p>
          </div>
        )}

        <div className="flex space-x-2 border-b border-slate-800 pb-px">
          <button
            onClick={() => setActiveTab("prediction")}
            className={`px-4 py-2.5 text-sm font-medium transition-colors border-b-2 ${activeTab === "prediction" ? "border-emerald-500 text-emerald-400" : "border-transparent text-slate-500 hover:text-slate-200 hover:border-slate-600"}`}
          >
            <div className="flex items-center gap-2">
              <Sparkles className="w-4 h-4"/> Akıllı Tahmin
            </div>
          </button>
          <button
            onClick={() => setActiveTab("raw")}
            className={`px-4 py-2.5 text-sm font-medium transition-colors border-b-2 ${activeTab === "raw" ? "border-indigo-500 text-indigo-400" : "border-transparent text-slate-500 hover:text-slate-200 hover:border-slate-600"}`}
          >
            <div className="flex items-center gap-2">
              <Database className="w-4 h-4"/> EPİAŞ Veri Matrisi
            </div>
          </button>
        </div>

        {activeTab === "prediction" ? renderPredictionTab() : renderRawDataTab()}

      </div>
    </div>
  );
}
