import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

/**
 * Phase B static documentation panel for the symbolic alpha DSL.
 * Mirrors the `SYMBOLIC_OPERATORS` + `SYMBOLIC_FIELDS` whitelist
 * from `aqp/data/expressions_dsl.py` so users in the Alpha Factor
 * Studio can browse the legal vocabulary without flipping back to
 * docs.
 *
 * Operator categories match the docstring grouping in
 * `aqp/data/expressions.py`. The panel surfaces a click-to-copy on
 * each token so users can paste straight into the editor.
 */

interface OperatorDoc {
  name: string;
  category: string;
  signature: string;
  description: string;
}

const OPERATORS: OperatorDoc[] = [
  // Rolling stats
  { name: "Mean", category: "rolling", signature: "Mean(x, w)", description: "Rolling mean over window w." },
  { name: "Std", category: "rolling", signature: "Std(x, w)", description: "Rolling stdev over window w." },
  { name: "Var", category: "rolling", signature: "Var(x, w)", description: "Rolling variance over window w." },
  { name: "Skew", category: "rolling", signature: "Skew(x, w)", description: "Rolling skewness." },
  { name: "Kurt", category: "rolling", signature: "Kurt(x, w)", description: "Rolling kurtosis." },
  { name: "Sum", category: "rolling", signature: "Sum(x, w)", description: "Rolling sum." },
  { name: "Min", category: "rolling", signature: "Min(x, w)", description: "Rolling min." },
  { name: "Max", category: "rolling", signature: "Max(x, w)", description: "Rolling max." },
  { name: "Med", category: "rolling", signature: "Med(x, w)", description: "Rolling median." },
  { name: "Mad", category: "rolling", signature: "Mad(x, w)", description: "Rolling mean absolute deviation." },
  { name: "Quantile", category: "rolling", signature: "Quantile(x, w, q)", description: "Rolling q-quantile." },
  { name: "Count", category: "rolling", signature: "Count(x, w)", description: "Non-NaN count in window." },
  { name: "IdxMax", category: "rolling", signature: "IdxMax(x, w)", description: "Bars-ago of rolling max." },
  { name: "IdxMin", category: "rolling", signature: "IdxMin(x, w)", description: "Bars-ago of rolling min." },
  { name: "EMA", category: "rolling", signature: "EMA(x, w)", description: "Exponential moving average." },
  { name: "WMA", category: "rolling", signature: "WMA(x, w)", description: "Linearly-weighted moving average." },
  { name: "Slope", category: "rolling", signature: "Slope(x, w)", description: "OLS slope of x vs index." },
  { name: "Rsquare", category: "rolling", signature: "Rsquare(x, w)", description: "OLS R^2 of x vs index." },
  { name: "Resi", category: "rolling", signature: "Resi(x, w)", description: "OLS residual." },
  // Lag / Ref
  { name: "Ref", category: "lag", signature: "Ref(x, n)", description: "Value n bars ago." },
  { name: "Delay", category: "lag", signature: "Delay(x, n)", description: "Alias for Ref." },
  // Pairwise rolling
  { name: "Corr", category: "pairwise", signature: "Corr(x, y, w)", description: "Rolling correlation." },
  { name: "Cov", category: "pairwise", signature: "Cov(x, y, w)", description: "Rolling covariance." },
  // Comparison
  { name: "Greater", category: "compare", signature: "Greater(x, y)", description: "Element-wise max." },
  { name: "Less", category: "compare", signature: "Less(x, y)", description: "Element-wise min." },
  { name: "Gt", category: "compare", signature: "Gt(x, y)", description: "x > y as 0/1." },
  { name: "Ge", category: "compare", signature: "Ge(x, y)", description: "x >= y as 0/1." },
  { name: "Lt", category: "compare", signature: "Lt(x, y)", description: "x < y as 0/1." },
  { name: "Le", category: "compare", signature: "Le(x, y)", description: "x <= y as 0/1." },
  { name: "Eq", category: "compare", signature: "Eq(x, y)", description: "x == y as 0/1." },
  { name: "Ne", category: "compare", signature: "Ne(x, y)", description: "x != y as 0/1." },
  // Logical
  { name: "And", category: "logical", signature: "And(x, y)", description: "Element-wise logical AND." },
  { name: "Or", category: "logical", signature: "Or(x, y)", description: "Element-wise logical OR." },
  { name: "Not", category: "logical", signature: "Not(x)", description: "Element-wise NOT." },
  // Conditional
  { name: "Mask", category: "conditional", signature: "Mask(cond, x)", description: "x where cond, else NaN." },
  { name: "If", category: "conditional", signature: "If(cond, a, b)", description: "Element-wise conditional." },
  // Arithmetic
  { name: "Add", category: "arith", signature: "Add(x, y)", description: "x + y." },
  { name: "Sub", category: "arith", signature: "Sub(x, y)", description: "x - y." },
  { name: "Mul", category: "arith", signature: "Mul(x, y)", description: "x * y." },
  { name: "Div", category: "arith", signature: "Div(x, y)", description: "x / y." },
  // DSL extensions
  { name: "Abs", category: "dsl", signature: "Abs(x)", description: "Element-wise absolute value." },
  { name: "Sign", category: "dsl", signature: "Sign(x)", description: "-1 / 0 / +1." },
  { name: "Log", category: "dsl", signature: "Log(x)", description: "Natural log (clipped to >=1e-12)." },
  { name: "Rank", category: "dsl", signature: "Rank(x)", description: "Percentile rank in [0, 1]." },
  { name: "Clip", category: "dsl", signature: "Clip(x, low, high)", description: "Element-wise clip." },
];

const FIELDS: ReadonlyArray<{ name: string; description: string }> = [
  { name: "$close", description: "Close price (canonical adjusted)" },
  { name: "$open", description: "Open price" },
  { name: "$high", description: "High price" },
  { name: "$low", description: "Low price" },
  { name: "$volume", description: "Volume (shares / contracts)" },
  { name: "$vwap", description: "Volume-weighted avg = (close+high+low)/3" },
  { name: "$returns", description: "Bar-over-bar pct change of close" },
];

const CATEGORY_LABELS: Record<string, string> = {
  rolling: "Rolling stats",
  lag: "Lag / reference",
  pairwise: "Pairwise rolling",
  compare: "Comparison",
  logical: "Logical",
  conditional: "Conditional",
  arith: "Arithmetic",
  dsl: "DSL extensions",
};

interface Props {
  /** Click handler — called with the token to insert (e.g. "Mean(x, w)" or "$close"). */
  onInsert?: (token: string) => void;
}

export function OperatorVocabPanel({ onInsert }: Props) {
  const [q, setQ] = useState("");
  const [category, setCategory] = useState<string>("");
  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return OPERATORS.filter((op) => {
      if (category && op.category !== category) return false;
      if (!needle) return true;
      return (
        op.name.toLowerCase().includes(needle) ||
        op.description.toLowerCase().includes(needle)
      );
    });
  }, [q, category]);

  const grouped = useMemo(() => {
    const groups: Record<string, OperatorDoc[]> = {};
    for (const op of filtered) {
      (groups[op.category] ??= []).push(op);
    }
    return groups;
  }, [filtered]);

  return (
    <Card className="flex h-full min-h-0 flex-col">
      <CardHeader>
        <CardTitle className="text-sm">DSL vocabulary</CardTitle>
      </CardHeader>
      <CardContent className="flex h-full min-h-0 flex-col gap-2 overflow-auto">
        <p className="text-[11px] text-[var(--text-secondary)]">
          The full whitelist enforced by the AST sandbox (rule 39). Click
          a token to insert it into the editor.
        </p>
        <Input
          placeholder="Search operators / descriptions..."
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="h-8"
        />
        <select
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          className="h-8 rounded-md border border-[var(--border-default)] bg-transparent px-2 text-xs"
        >
          <option value="">All categories</option>
          {Object.entries(CATEGORY_LABELS).map(([k, label]) => (
            <option key={k} value={k}>
              {label}
            </option>
          ))}
        </select>
        <div>
          <div className="mb-1 text-[11px] uppercase tracking-wide text-[var(--text-secondary)]">
            Fields
          </div>
          <div className="flex flex-wrap gap-1">
            {FIELDS.map((f) => (
              <button
                key={f.name}
                type="button"
                title={f.description}
                onClick={() => onInsert?.(f.name)}
                className="rounded border border-[var(--border-default)] px-2 py-0.5 font-mono text-[11px] hover:bg-[var(--bg-elevated)]"
              >
                {f.name}
              </button>
            ))}
          </div>
        </div>
        {Object.entries(grouped).map(([cat, ops]) => (
          <div key={cat}>
            <div className="mb-1 mt-2 flex items-center gap-2 text-[11px] uppercase tracking-wide text-[var(--text-secondary)]">
              {CATEGORY_LABELS[cat] ?? cat}
              <Badge variant="outline">{ops.length}</Badge>
            </div>
            <div className="grid gap-1">
              {ops.map((op) => (
                <button
                  key={op.name}
                  type="button"
                  onClick={() => onInsert?.(op.signature)}
                  className="grid grid-cols-[minmax(110px,140px)_1fr] items-baseline gap-2 rounded border border-[var(--border-default)] px-2 py-1 text-left text-[11px] hover:bg-[var(--bg-elevated)]"
                >
                  <span className="font-mono text-[var(--info-fg)]">{op.signature}</span>
                  <span className="text-[var(--text-secondary)]">{op.description}</span>
                </button>
              ))}
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
