import { useCallback, useRef, useState } from "react";
import Icon, { type IconName } from "./Icon";

// A button that runs an async action and briefly shows a confirmation label
// (e.g. "Copied!", "Exported") so clicks always give visible feedback.
export default function ActionButton({
  label,
  doneLabel = "Done",
  icon,
  onAct,
  className = "btn btn-sm",
  title,
}: {
  label: string;
  doneLabel?: string;
  icon?: IconName;
  onAct: () => void | Promise<void> | boolean | Promise<boolean>;
  className?: string;
  title?: string;
}) {
  const [done, setDone] = useState(false);
  const timer = useRef<number | undefined>(undefined);
  const handle = useCallback(async () => {
    const ok = await onAct();
    if (ok === false) return;
    setDone(true);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setDone(false), 1600);
  }, [onAct]);
  return (
    <button className={className} onClick={handle} title={title}>
      {icon && <Icon name={done ? "check" : icon} size={13} />}
      {done ? doneLabel : label}
    </button>
  );
}
