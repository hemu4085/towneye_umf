"use client";

type RangeFieldProps = {
  label: string;
  hint?: string;
  value: string | number;
  min?: number;
  max?: number;
  step?: number;
  onChange: (value: string) => void;
};

export default function RangeField({
  label,
  hint,
  value,
  min = 0,
  max = 100,
  step = 1,
  onChange,
}: RangeFieldProps) {
  const num = value === "" ? min : Number(value);
  const safe = Number.isFinite(num) ? num : min;

  return (
    <label className="block text-xs text-gray-400">
      <div className="flex justify-between items-baseline mb-1">
        <span>{label}</span>
        <span className="text-white font-mono text-sm tabular-nums">{safe}</span>
      </div>
      {hint && <span className="block text-[10px] text-gray-500 mb-1">{hint}</span>}
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={safe}
        onChange={(e) => onChange(e.target.value)}
        className="w-full accent-blue-500 h-2 mb-1"
      />
      <input
        type="number"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full bg-gray-950 border border-gray-700 rounded-lg px-2 py-1 text-sm text-white"
      />
    </label>
  );
}
