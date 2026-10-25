// Shared building blocks. Every screen is built from these, so the whole look lives here + theme.ts.
import React, { useCallback, useEffect, useState } from "react";
import { Text as RNText, TextProps, TextInput, View, ScrollView, ActivityIndicator, Pressable, TextInputProps,
  StyleSheet, useWindowDimensions, Platform } from "react-native";
import { Link, Href, usePathname } from "expo-router";
import { BlurView } from "expo-blur";
import { LinearGradient } from "expo-linear-gradient";
import { Feather } from "@expo/vector-icons";
import { apiList, api, errorText } from "./api";
import { theme as t } from "./theme";

export { View };
export type IconName = React.ComponentProps<typeof Feather>["name"];
export const Icon = ({ name, size = 20, color = t.color.ink }: { name: IconName; size?: number; color?: string }) => (
  <Feather name={name} size={size} color={color} />
);
export const kes = (v: any) => `KES ${Number(v ?? 0).toLocaleString("en-KE", { maximumFractionDigits: 2 })}`;

export const Text = ({ style, ...p }: TextProps) => (
  <RNText style={[{ color: t.color.ink, fontSize: t.font.body, lineHeight: 21, marginBottom: t.space.xs, fontFamily: t.family as any }, style]} {...p} />
);

// ------------------------------------------------------------------ glass surface
/** Frosted panel: real backdrop blur + translucent fill + specular highlight + bright edge. */
export function Glass({ children, style, pad = t.space.lg, radius = t.radiusLg, strong, blur = t.glass.blur }:
  { children?: React.ReactNode; style?: any; pad?: number; radius?: number; strong?: boolean; blur?: number }) {
  return (
    <View style={[{ borderRadius: radius, overflow: "hidden", borderWidth: 1, borderColor: t.color.border, boxShadow: t.glass.shadow }, style]}>
      <BlurView intensity={blur} tint="light" style={StyleSheet.absoluteFill} />
      <View pointerEvents="none" style={[StyleSheet.absoluteFill, { backgroundColor: strong ? t.glass.strong : t.glass.fill }]} />
      <LinearGradient pointerEvents="none" colors={["rgba(255,255,255,0.65)", "rgba(255,255,255,0)"]} start={{ x: 0, y: 0 }} end={{ x: 0.7, y: 0.9 }} style={StyleSheet.absoluteFill} />
      <View style={{ padding: pad }}>{children}</View>
    </View>
  );
}
export const Card = ({ children, style, pad }: { children: React.ReactNode; style?: any; pad?: number }) => (
  <Glass pad={pad} style={[{ marginBottom: t.space.md }, style]}>{children}</Glass>
);

/** Page backdrop: pastel gradient with soft colour blobs the glass can refract. */
export function Backdrop() {
  const web = Platform.OS === "web";
  const spots: [number, number, number, number][] = [[-120, -80, 460, 0], [undefined as any, -140, 520, 1], [-80, undefined as any, 440, 2], [undefined as any, undefined as any, 360, 3]];
  const pos = [{ top: -120, left: -100 }, { top: 60, right: -160 }, { bottom: -140, left: -60 }, { bottom: 120, right: 40 }];
  return (
    <View pointerEvents="none" style={StyleSheet.absoluteFill}>
      <LinearGradient colors={t.backdrop} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={StyleSheet.absoluteFill} />
      {spots.map(([, , size, i]) => (
        <View key={i} style={[{ position: "absolute", width: size, height: size, borderRadius: size / 2, backgroundColor: t.blobs[i], opacity: web ? 0.5 : 0.28 }, pos[i] as any, web ? ({ filter: "blur(70px)" } as any) : null]} />
      ))}
    </View>
  );
}

export const Screen = ({ title, subtitle, children }: { title?: string; subtitle?: string; children: React.ReactNode }) => (
  <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: t.space.lg, paddingBottom: 120, alignItems: "center" }} showsVerticalScrollIndicator={false}>
    <View style={{ width: "100%", maxWidth: t.maxWidth }}>
      {title ? <Text accessibilityRole="header" style={{ fontSize: t.font.title, fontWeight: "800", letterSpacing: -0.6, lineHeight: 34, marginBottom: subtitle ? 2 : t.space.md }}>{title}</Text> : null}
      {subtitle ? <Text style={{ color: t.color.muted, marginBottom: t.space.lg }}>{subtitle}</Text> : null}
      {children}
    </View>
  </ScrollView>
);
export const Gap = () => <View style={{ height: t.space.md }} />;
export const Section = ({ children }: { children: React.ReactNode }) => (
  <Text style={{ fontSize: t.font.section, fontWeight: "700", letterSpacing: -0.3, marginTop: t.space.xl, marginBottom: t.space.sm }}>{children}</Text>
);

// ------------------------------------------------------------------ inputs and buttons
export const Field = ({ label, ...p }: { label: string } & TextInputProps) => {
  const [focus, setFocus] = useState(false);
  return (
    <View style={{ marginBottom: t.space.md }}>
      <Text style={{ fontSize: 12, fontWeight: "700", color: t.color.muted, letterSpacing: 0.4, textTransform: "uppercase", marginBottom: 6 }}>{label}</Text>
      <TextInput autoCapitalize="none" placeholderTextColor={t.color.faint}
        onFocus={() => setFocus(true)} onBlur={() => setFocus(false)}
        style={[{ backgroundColor: "rgba(255,255,255,0.72)", borderColor: focus ? t.color.primary : "rgba(255,255,255,0.95)", borderWidth: 1.5, borderRadius: 10,
          paddingVertical: 13, paddingHorizontal: 16, fontSize: 16, color: t.color.ink, fontFamily: t.family as any,
          boxShadow: focus ? "0 0 0 4px rgba(16,185,129,0.18)" : "0 1px 2px rgba(20,60,48,0.06)" }, { outlineWidth: 0 } as any]} {...p} />
    </View>
  );
};

export const Btn = ({ title, onPress, disabled, kind = "primary", icon }: { title: string; onPress: () => void; disabled?: boolean; kind?: "primary" | "plain"; icon?: IconName }) => {
  const primary = kind === "primary";
  const body = (
    <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "center", paddingVertical: 14, paddingHorizontal: t.space.lg }}>
      {icon ? <View style={{ marginRight: 8 }}><Icon name={icon} size={18} color={primary ? "#fff" : t.color.ink} /></View> : null}
      <Text style={{ color: primary ? "#fff" : t.color.ink, fontWeight: "700", marginBottom: 0, letterSpacing: -0.1 }}>{title}</Text>
    </View>
  );
  return (
    <Pressable onPress={onPress} disabled={disabled} accessibilityRole="button"
      style={({ pressed }) => ({ opacity: disabled ? 0.45 : 1, transform: [{ scale: pressed ? 0.98 : 1 }], marginBottom: t.space.sm,
        borderRadius: 12, overflow: "hidden", borderWidth: 1, borderColor: primary ? "rgba(255,255,255,0.35)" : t.color.border,
        backgroundColor: primary ? undefined : "rgba(255,255,255,0.6)",
        boxShadow: primary ? "0 8px 22px rgba(14,159,110,0.38), inset 0 1px 0 rgba(255,255,255,0.35)" : "0 2px 8px rgba(20,60,48,0.08)" })}>
      {primary ? <LinearGradient colors={t.gradient.brand} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }}>{body}</LinearGradient> : body}
    </Pressable>
  );
};

/** Tappable list row. */
export const Nav = ({ href, children, icon }: { href: Href; children: React.ReactNode; icon?: IconName }) => (
  <Link href={href} asChild>
    <Pressable style={({ pressed }) => ({ marginBottom: t.space.sm, transform: [{ scale: pressed ? 0.99 : 1 }] })}>
      <Glass pad={14} radius={12}>
        <View style={{ flexDirection: "row", alignItems: "center" }}>
          {icon ? <View style={{ marginRight: 12 }}><Icon name={icon} size={20} color={t.color.primary} /></View> : null}
          <Text style={{ flex: 1, fontWeight: "600", marginBottom: 0 }}>{children}</Text>
          <Icon name="chevron-right" size={18} color={t.color.faint} />
        </View>
      </Glass>
    </Pressable>
  </Link>
);

export const ErrorText = ({ error }: { error?: string | null }) =>
  error ? (
    <View style={{ backgroundColor: t.color.dangerBg, borderRadius: 10, padding: t.space.md, marginBottom: t.space.md, flexDirection: "row", alignItems: "center" }}>
      <Icon name="alert-circle" size={18} color={t.color.danger} />
      <Text style={{ color: t.color.danger, marginBottom: 0, marginLeft: 8, flex: 1 }}>{error}</Text>
    </View>
  ) : null;

// ------------------------------------------------------------------ data helpers
export function useLoad<T = any>(path: string | null, list = false) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(!!path);
  const reload = useCallback(async () => {
    if (!path) return;
    setLoading(true); setError(null);
    try { setData((list ? await apiList(path) : await api(path)) as T); } catch (e) { setError(errorText(e)); }
    setLoading(false);
  }, [path, list]);
  useEffect(() => { reload(); }, [reload]);
  return { data, error, loading, reload };
}
export const Loading = ({ loading, error }: { loading: boolean; error: string | null }) =>
  loading ? <ActivityIndicator color={t.color.primary} style={{ margin: t.space.lg }} /> : <ErrorText error={error} />;
export function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = async <T,>(fn: () => Promise<T>): Promise<T | undefined> => {
    setBusy(true); setError(null);
    try { return await fn(); } catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  };
  return { busy, error, run };
}

// ------------------------------------------------------------------ storefront pieces
export function Grid({ children, min = 220 }: { children: React.ReactNode; min?: number }) {
  const { width } = useWindowDimensions();
  const inner = Math.min(width, t.maxWidth + 32) - 32;
  const cols = Math.max(1, Math.min(4, Math.floor(inner / min)));
  return (
    <View style={{ flexDirection: "row", flexWrap: "wrap", marginHorizontal: -6 }}>
      {React.Children.toArray(children).map((c, i) => <View key={i} style={{ width: `${100 / cols}%`, padding: 6 }}>{c}</View>)}
    </View>
  );
}

const DUOS: [string, string][] = [["#12B886", "#0B8A6B"], ["#3B82F6", "#1D4ED8"], ["#8B5CF6", "#6D28D9"], ["#F59E0B", "#D97706"], ["#EC4899", "#BE185D"], ["#14B8A6", "#0F766E"], ["#F97316", "#C2410C"]];
const duo = (name: string) => DUOS[[...(name || "?")].reduce((a, c) => a + c.charCodeAt(0), 0) % DUOS.length];

export const Avatar = ({ name, size = 46 }: { name: string; size?: number }) => (
  <LinearGradient colors={duo(name)} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }}
    style={{ width: size, height: size, borderRadius: size * 0.24, alignItems: "center", justifyContent: "center", boxShadow: "0 6px 14px rgba(20,60,48,0.22)" }}>
    <Text style={{ color: "#fff", fontWeight: "800", fontSize: size * 0.42, lineHeight: size * 0.5, marginBottom: 0 }}>{(name || "?").trim().charAt(0).toUpperCase()}</Text>
  </LinearGradient>
);

const PILL: Record<string, [string, string]> = {
  good: [t.color.primaryDark, t.color.primarySoft], warn: [t.color.warn, t.color.warnBg], bad: [t.color.danger, t.color.dangerBg],
  info: [t.color.info, t.color.infoBg], neutral: [t.color.muted, "rgba(11,31,25,0.07)"],
};
export const Pill = ({ children, tone = "neutral" }: { children: React.ReactNode; tone?: keyof typeof PILL }) => (
  <View style={{ alignSelf: "flex-start", flexDirection: "row", alignItems: "center", backgroundColor: PILL[tone][1], borderRadius: 999, paddingHorizontal: 10, paddingVertical: 4, marginRight: 6, marginBottom: 4 }}>
    <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: PILL[tone][0], marginRight: 6 }} />
    <Text style={{ color: PILL[tone][0], fontSize: 12, fontWeight: "700", marginBottom: 0, lineHeight: 16 }}>{children}</Text>
  </View>
);
export const statusTone = (s: string): keyof typeof PILL =>
  ({ submitted: "info", confirmed: "info", dispatched: "warn", received: "good", approved: "good", open: "good", closed: "warn",
     cancelled: "bad", rejected: "bad", declined: "bad", failed: "bad", in_progress: "info" } as any)[s] ?? "neutral";

export const ProgressBar = ({ value }: { value: number }) => (
  <View style={{ height: 10, backgroundColor: "rgba(11,31,25,0.08)", borderRadius: 5, overflow: "hidden", marginVertical: t.space.sm }}>
    <LinearGradient colors={t.gradient.brand} start={{ x: 0, y: 0 }} end={{ x: 1, y: 0 }} style={{ width: `${Math.max(2, Math.min(100, value * 100))}%`, height: 10, borderRadius: 5 }} />
  </View>
);

export const Stat = ({ label, value, tone, icon }: { label: string; value: React.ReactNode; tone?: "bad" | "warn"; icon?: IconName }) => {
  const c = tone === "bad" ? t.color.danger : tone === "warn" ? t.color.warn : t.color.ink;
  return (
    <Glass pad={16} radius={14}>
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" }}>
        <Text style={{ color: t.color.muted, fontSize: 12, fontWeight: "700", letterSpacing: 0.4, textTransform: "uppercase", flex: 1 }}>{label}</Text>
        {icon ? <Icon name={icon} size={16} color={t.color.faint} /> : null}
      </View>
      <Text style={{ fontSize: 32, fontWeight: "800", letterSpacing: -1, lineHeight: 38, marginBottom: 0, color: c }}>{value}</Text>
    </Glass>
  );
};

export const Tile = ({ href, icon, label, badge }: { href: Href; icon: IconName; label: string; badge?: string | number }) => (
  <Link href={href} asChild>
    <Pressable style={({ pressed }) => ({ transform: [{ scale: pressed ? 0.97 : 1 }] })}>
      <Glass pad={16} radius={14}>
        <LinearGradient colors={duo(label)} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }}
          style={{ width: 42, height: 42, borderRadius: 10, alignItems: "center", justifyContent: "center", marginBottom: 12, boxShadow: "0 6px 14px rgba(20,60,48,0.2)" }}>
          <Icon name={icon} size={20} color="#fff" />
        </LinearGradient>
        <Text style={{ fontWeight: "700", marginBottom: 0, letterSpacing: -0.2 }}>{label}</Text>
        {badge ? <View style={{ position: "absolute", top: 12, right: 12 }}><Pill tone="bad">{badge}</Pill></View> : null}
      </Glass>
    </Pressable>
  </Link>
);

export const ProductCard = ({ href, name, subtitle, price, priceNote, pills, footer }:
  { href: Href; name: string; subtitle?: string; price?: string; priceNote?: string; pills?: React.ReactNode; footer?: React.ReactNode }) => (
  <Link href={href} asChild>
    <Pressable style={({ pressed }) => ({ transform: [{ scale: pressed ? 0.985 : 1 }] })}>
      <Glass pad={0} radius={14}>
        <LinearGradient colors={duo(name)} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={{ height: 96, justifyContent: "flex-end", padding: 14, overflow: "hidden" }}>
          <View style={{ position: "absolute", right: -26, top: -30, width: 120, height: 120, borderRadius: 60, backgroundColor: "rgba(255,255,255,0.18)" }} />
          <View style={{ position: "absolute", right: 40, bottom: -50, width: 90, height: 90, borderRadius: 45, backgroundColor: "rgba(255,255,255,0.12)" }} />
          <Text style={{ color: "#fff", fontSize: 38, fontWeight: "800", letterSpacing: -1, lineHeight: 42, marginBottom: 0 }}>{(name || "?").charAt(0).toUpperCase()}</Text>
        </LinearGradient>
        <View style={{ padding: 14 }}>
          <Text style={{ fontWeight: "700", fontSize: 16, letterSpacing: -0.2, marginBottom: 2 }} numberOfLines={2}>{name}</Text>
          {subtitle ? <Text style={{ color: t.color.muted, fontSize: t.font.small }} numberOfLines={1}>{subtitle}</Text> : null}
          {price ? <Text style={{ fontSize: 22, fontWeight: "800", letterSpacing: -0.6, color: t.color.primaryDark, marginTop: 4, marginBottom: 0 }}>{price}
            {priceNote ? <Text style={{ fontSize: 12, color: t.color.muted, fontWeight: "500", letterSpacing: 0 }}>  {priceNote}</Text> : null}</Text> : null}
          {pills ? <View style={{ flexDirection: "row", flexWrap: "wrap", marginTop: t.space.sm }}>{pills}</View> : null}
          {footer}
        </View>
      </Glass>
    </Pressable>
  </Link>
);

export const Banner = ({ href, tone = "warn", icon, children }: { href?: Href; tone?: "warn" | "info"; icon?: IconName; children: React.ReactNode }) => {
  const c = tone === "warn" ? t.color.warn : t.color.info;
  const inner = (
    <View style={{ backgroundColor: tone === "warn" ? t.color.warnBg : t.color.infoBg, borderRadius: 12, padding: t.space.md, marginBottom: t.space.md, flexDirection: "row", alignItems: "center", borderWidth: 1, borderColor: t.color.border }}>
      <Icon name={icon ?? (tone === "warn" ? "alert-triangle" : "cloud-off")} size={18} color={c} />
      <Text style={{ color: c, fontWeight: "600", marginBottom: 0, marginLeft: 10, flex: 1 }}>{children}</Text>
      {href ? <Icon name="chevron-right" size={18} color={c} /> : null}
    </View>);
  return href ? <Link href={href} asChild><Pressable>{inner}</Pressable></Link> : inner;
};

/** Floating glass tab bar for shop pages. */
export function BottomNav({ shopId }: { shopId: string }) {
  const path = usePathname();
  const base = `/shops/${shopId}`;
  const items: [string, IconName, string, (p: string) => boolean][] = [
    ["Home", "home", base, (p) => p === base],
    ["Stock", "package", `${base}/inventory`, (p) => /\/(inventory|alerts|counts|movements)/.test(p)],
    ["Sell", "shopping-bag", `${base}/sell`, (p) => p.includes("/sell") || p.includes("/receive")],
    ["Market", "compass", `${base}/market`, (p) => p.includes("/market") || p.includes("/groups")],
    ["Orders", "truck", `${base}/orders`, (p) => p.includes("/orders")],
  ];
  return (
    <View pointerEvents="box-none" style={{ position: "absolute", left: 0, right: 0, bottom: 14, alignItems: "center" }}>
      <Glass pad={6} radius={20} strong style={{ width: "92%", maxWidth: 520 }}>
        <View style={{ flexDirection: "row" }}>
          {items.map(([label, icon, href, active]) => {
            const on = active(path);
            return (
              <Link key={label} href={href as Href} asChild>
                <Pressable style={{ flex: 1, alignItems: "center", paddingVertical: 8, borderRadius: 14, backgroundColor: on ? t.color.primarySoft : "transparent" }}>
                  <Icon name={icon} size={20} color={on ? t.color.primaryDark : t.color.muted} />
                  <Text style={{ fontSize: 11, marginTop: 3, marginBottom: 0, lineHeight: 14, fontWeight: on ? "800" : "600", color: on ? t.color.primaryDark : t.color.muted }}>{label}</Text>
                </Pressable>
              </Link>
            );
          })}
        </View>
      </Glass>
    </View>
  );
}
