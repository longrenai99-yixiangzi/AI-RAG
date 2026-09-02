export function CoverageBar({ value }: { value: number }) {
  return <div className="coverage"><div className="coverage-track"><i style={{ width: `${value}%` }} /></div><span>{value}%</span></div>
}
