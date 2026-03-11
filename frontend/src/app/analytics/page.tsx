"use client";

import { useQuery } from "@tanstack/react-query";
import { analyticsApi, type AnalyticsResponse } from "@/lib/api";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
} from "recharts";
import { BarChart2, AlertTriangle, Calendar } from "lucide-react";

const BRAND_COLORS = [
  "#2563eb", "#3b82f6", "#60a5fa", "#93c5fd", "#bfdbfe",
  "#1d4ed8", "#1e40af", "#1e3a8a", "#172554", "#dbeafe",
];

function StatCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="card p-5">
      <p className="section-label mb-1">{label}</p>
      <p className="text-2xl font-bold text-slate-900">{value}</p>
      {sub && <p className="text-xs text-slate-400 mt-0.5">{sub}</p>}
    </div>
  );
}

export default function AnalyticsPage() {
  const { data, isLoading, isError } = useQuery<AnalyticsResponse>({
    queryKey: ["analytics"],
    queryFn: () => analyticsApi.get({ months: 12, expiry_days: 180 }),
  });

  if (isLoading) {
    return (
      <div className="px-8 py-8 max-w-6xl">
        <p className="section-label">Intelligence</p>
        <h1 className="mb-8">Analytics</h1>
        <div className="grid grid-cols-3 gap-4 mb-8">
          {[0, 1, 2].map((i) => (
            <div key={i} className="card p-5 animate-pulse">
              <div className="h-3 w-24 bg-slate-200 rounded mb-3" />
              <div className="h-8 w-16 bg-slate-200 rounded" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="px-8 py-8 max-w-6xl">
        <p className="section-label">Intelligence</p>
        <h1 className="mb-4">Analytics</h1>
        <div className="card p-8 text-center">
          <AlertTriangle className="h-8 w-8 text-amber-400 mx-auto mb-2" />
          <p className="text-sm text-slate-500">Could not load analytics. Ensure the analytics migration has run.</p>
        </div>
      </div>
    );
  }

  const { spend_by_month, vendor_concentration, upcoming_expiries } = data;

  // Summary stats
  const totalDocs = spend_by_month.reduce((s, p) => s + p.document_count, 0);
  const totalInvoices = spend_by_month.reduce((s, p) => s + p.total_invoices, 0);
  const expiresIn30 = upcoming_expiries.filter((e) => e.days_until_expiry <= 30).length;

  return (
    <div className="px-8 py-8 max-w-6xl">
      <p className="section-label">Intelligence</p>
      <h1 className="mb-1">Analytics</h1>
      <p className="mb-8 text-sm text-slate-500">
        Spend trends, vendor concentration, and upcoming contract expiries — last 12 months.
      </p>

      {/* Summary stats */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
        <StatCard label="Total Documents (12 mo)" value={totalDocs.toLocaleString()} />
        <StatCard
          label="Total Invoices (12 mo)"
          value={totalInvoices.toLocaleString()}
          sub="documents categorised as invoices"
        />
        <StatCard
          label="Contracts Expiring ≤ 30 days"
          value={expiresIn30}
          sub={`${upcoming_expiries.length} expiring within 180 days`}
        />
      </div>

      {/* Spend trend */}
      <div className="card p-6 mb-6">
        <div className="flex items-center gap-2 mb-4">
          <BarChart2 className="h-4 w-4 text-brand-500" />
          <h2 className="font-semibold text-slate-800 text-sm">Document Volume by Month</h2>
        </div>
        {spend_by_month.length === 0 ? (
          <p className="text-sm text-slate-400 text-center py-8">No data yet.</p>
        ) : (
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={spend_by_month} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis
                dataKey="period"
                tick={{ fontSize: 11, fill: "#94a3b8" }}
                tickLine={false}
                axisLine={false}
              />
              <YAxis tick={{ fontSize: 11, fill: "#94a3b8" }} tickLine={false} axisLine={false} />
              <Tooltip
                contentStyle={{ borderRadius: 8, border: "1px solid #e2e8f0", fontSize: 12 }}
                cursor={{ fill: "#f8fafc" }}
              />
              <Bar dataKey="document_count" name="Documents" fill="#2563eb" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        {/* Vendor concentration */}
        <div className="card p-6">
          <h2 className="font-semibold text-slate-800 text-sm mb-4">Top Vendor Concentration</h2>
          {vendor_concentration.length === 0 ? (
            <p className="text-sm text-slate-400 text-center py-8">No vendor data yet.</p>
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie
                  data={vendor_concentration}
                  dataKey="document_count"
                  nameKey="vendor_name"
                  cx="50%"
                  cy="50%"
                  outerRadius={90}
                  label={({ name, value }: { name?: string; value?: number }) => {
                    const label = (name ?? "").slice(0, 14);
                    return value ? `${label} (${value})` : label;
                  }}
                  labelLine={false}
                >
                  {vendor_concentration.map((_, idx) => (
                    <Cell key={idx} fill={BRAND_COLORS[idx % BRAND_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip
                  formatter={(val, name) => [`${val ?? 0} docs`, String(name)]}
                  contentStyle={{ borderRadius: 8, border: "1px solid #e2e8f0", fontSize: 12 }}
                />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Upcoming expiries */}
        <div className="card p-6">
          <div className="flex items-center gap-2 mb-4">
            <Calendar className="h-4 w-4 text-amber-500" />
            <h2 className="font-semibold text-slate-800 text-sm">Upcoming Contract Expiries</h2>
          </div>
          {upcoming_expiries.length === 0 ? (
            <p className="text-sm text-slate-400 text-center py-8">No contracts expiring in the next 180 days.</p>
          ) : (
            <div className="overflow-auto max-h-[240px]">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-slate-100">
                    <th className="text-left py-2 text-slate-400 font-medium">Vendor</th>
                    <th className="text-left py-2 text-slate-400 font-medium">Expiry</th>
                    <th className="text-right py-2 text-slate-400 font-medium">Days</th>
                    <th className="text-right py-2 text-slate-400 font-medium">Value</th>
                  </tr>
                </thead>
                <tbody>
                  {upcoming_expiries.map((e) => (
                    <tr key={e.document_id} className="border-b border-slate-50 hover:bg-slate-50">
                      <td className="py-2 text-slate-700 font-medium truncate max-w-[120px]">
                        {e.vendor_name ?? "—"}
                      </td>
                      <td className="py-2 text-slate-500">{e.contract_end_date}</td>
                      <td
                        className={`py-2 text-right font-semibold ${
                          e.days_until_expiry <= 30
                            ? "text-red-600"
                            : e.days_until_expiry <= 90
                            ? "text-amber-600"
                            : "text-slate-600"
                        }`}
                      >
                        {e.days_until_expiry}d
                      </td>
                      <td className="py-2 text-right text-slate-500">
                        {e.contract_value ?? "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
