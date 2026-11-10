import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/** Thẻ số liệu trên trang chủ. `soon` = chức năng sprint sau: viền đứt, chữ mờ. */
export function StatCard({
  label,
  value,
  hint,
  soon,
}: {
  label: string;
  value?: string;
  hint?: string;
  soon?: boolean;
}) {
  return (
    <Card className={cn(soon && "border-dashed text-muted-foreground shadow-none")}>
      <CardHeader>
        <CardDescription>{label}</CardDescription>
        <CardTitle className="text-2xl">{value ?? "—"}</CardTitle>
      </CardHeader>
      {hint && <CardContent className="text-xs text-muted-foreground">{hint}</CardContent>}
    </Card>
  );
}

export function PageShell({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mx-auto grid w-full max-w-6xl gap-5 px-4 py-8">
      <h1 className="text-2xl font-semibold">{title}</h1>
      {children}
    </div>
  );
}
