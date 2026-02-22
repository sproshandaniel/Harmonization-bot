type FlowStep = {
  stepNo: number;
  title: string;
  dependsOn: number[];
};

type WizardFlowchartProps = {
  steps: FlowStep[];
  currentStep?: number | null;
  className?: string;
};

function nodeColor(stepNo: number, currentStep?: number | null): string {
  if (currentStep == null) return "#3b82f6";
  if (stepNo < currentStep) return "#16a34a";
  if (stepNo === currentStep) return "#2563eb";
  return "#9ca3af";
}

export default function WizardFlowchart({ steps, currentStep = null, className = "" }: WizardFlowchartProps) {
  const ordered = [...steps].sort((a, b) => a.stepNo - b.stepNo);
  if (ordered.length === 0) {
    return (
      <div className={`rounded border border-gray-200 bg-gray-50 px-3 py-2 text-xs text-gray-600 ${className}`}>
        No workflow steps available.
      </div>
    );
  }

  const spacingX = 220;
  const startX = 90;
  const y = 84;
  const width = Math.max(700, startX * 2 + (ordered.length - 1) * spacingX);
  const height = 220;

  const idxByStep = new Map<number, number>();
  ordered.forEach((step, idx) => idxByStep.set(step.stepNo, idx));

  return (
    <div className={`w-full overflow-x-auto rounded border border-gray-200 bg-white ${className}`}>
      <svg width={width} height={height} role="img" aria-label="Wizard step workflow chart">
        <defs>
          <marker id="wfArrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
            <path d="M0,0 L8,4 L0,8 z" fill="#64748b" />
          </marker>
          <marker id="wfArrowDashed" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
            <path d="M0,0 L8,4 L0,8 z" fill="#94a3b8" />
          </marker>
        </defs>

        {ordered.map((_, idx) => {
          if (idx === ordered.length - 1) return null;
          const x1 = startX + idx * spacingX + 20;
          const x2 = startX + (idx + 1) * spacingX - 20;
          return (
            <line
              key={`seq-${idx}`}
              x1={x1}
              y1={y}
              x2={x2}
              y2={y}
              stroke="#64748b"
              strokeWidth="2"
              markerEnd="url(#wfArrow)"
            />
          );
        })}

        {ordered.map((step) =>
          step.dependsOn
            .filter((dep) => dep !== step.stepNo)
            .map((dep) => {
              const fromIdx = idxByStep.get(dep);
              const toIdx = idxByStep.get(step.stepNo);
              if (fromIdx == null || toIdx == null || fromIdx >= toIdx) return null;
              if (toIdx === fromIdx + 1) return null;
              const x1 = startX + fromIdx * spacingX;
              const x2 = startX + toIdx * spacingX;
              const ctrlY = y - 54;
              const d = `M ${x1} ${y - 24} C ${x1 + 40} ${ctrlY}, ${x2 - 40} ${ctrlY}, ${x2} ${y - 24}`;
              return (
                <path
                  key={`dep-${dep}-${step.stepNo}`}
                  d={d}
                  fill="none"
                  stroke="#94a3b8"
                  strokeWidth="1.8"
                  strokeDasharray="5 4"
                  markerEnd="url(#wfArrowDashed)"
                />
              );
            })
        )}

        {ordered.map((step, idx) => {
          const x = startX + idx * spacingX;
          const color = nodeColor(step.stepNo, currentStep);
          return (
            <g key={`node-${step.stepNo}`}>
              <circle cx={x} cy={y} r={20} fill={color} />
              <text x={x} y={y + 5} textAnchor="middle" fontSize="12" fontWeight="700" fill="#ffffff">
                {step.stepNo}
              </text>
              <rect x={x - 88} y={118} width={176} height={64} rx={8} ry={8} fill="#f8fafc" stroke="#cbd5e1" />
              <text
                x={x}
                y={136}
                textAnchor="middle"
                fontSize="11"
                fontWeight="600"
                fill="#0f172a"
              >
                {step.title.length > 30 ? `${step.title.slice(0, 30)}...` : step.title}
              </text>
              {step.dependsOn.length > 0 && (
                <text x={x} y={155} textAnchor="middle" fontSize="10" fill="#475569">
                  deps: {step.dependsOn.join(", ")}
                </text>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

