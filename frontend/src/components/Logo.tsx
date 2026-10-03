// The marketing site's wordmark (docs/index.html .logo): three bucket dots
// and "CRM Scoring" in the display serif, "Scoring" in the accent.
export function Logo({ className = "" }: { className?: string }) {
  return (
    <span className={`inline-flex items-center gap-2 ${className}`}>
      <span aria-hidden="true" className="flex gap-[3px]">
        <span className="block h-[7px] w-[7px] rounded-full bg-hot" />
        <span className="block h-[7px] w-[7px] rounded-full bg-warm" />
        <span className="block h-[7px] w-[7px] rounded-full bg-cold" />
      </span>
      <span className="font-display text-[1.2rem] font-semibold tracking-tight text-heading">
        CRM <span className="text-accent">Scoring</span>
      </span>
    </span>
  );
}
