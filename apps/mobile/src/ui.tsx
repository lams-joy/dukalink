// Deliberately unstyled building blocks. Whoever does the CSS/theme can restyle these in one place.
import React, { useCallback, useEffect, useState } from "react";
import { Text, TextInput, View, Button, ScrollView, ActivityIndicator, TextInputProps } from "react-native";
import { Link, Href } from "expo-router";
import { apiList, api, errorText } from "./api";

export const Screen = ({ title, children }: { title?: string; children: React.ReactNode }) => (
  <ScrollView contentContainerStyle={{ padding: 16 }}>
    {title ? <Text accessibilityRole="header">{title}</Text> : null}
    {children}
  </ScrollView>
);
export const Gap = () => <View style={{ height: 12 }} />;
export const Nav = ({ href, children }: { href: Href; children: React.ReactNode }) => (
  <Link href={href}><Text>{children}</Text></Link>
);
export const Field = ({ label, ...p }: { label: string } & TextInputProps) => (
  <View><Text>{label}</Text><TextInput autoCapitalize="none" {...p} /></View>
);
export const Btn = ({ title, onPress, disabled }: { title: string; onPress: () => void; disabled?: boolean }) => (
  <Button title={title} onPress={onPress} disabled={disabled} />
);
export const ErrorText = ({ error }: { error?: string | null }) => (error ? <Text>Error: {error}</Text> : null);

/** Load a paginated list or a single object; returns state plus reload. */
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
  loading ? <ActivityIndicator /> : <ErrorText error={error} />;

/** Run a write; tracks busy/error/result so forms stay tiny. */
export function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = async <T,>(fn: () => Promise<T>): Promise<T | undefined> => {
    setBusy(true); setError(null);
    try { return await fn(); } catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  };
  return { busy, error, run };
}
