import { useState } from "react";
import Icon from "./Icon";

// Expandable card used for evidence / reasoning sections in chat responses.
export default function Collapsible({
  title,
  icon = "file",
  defaultOpen = false,
  children,
}: {
  title: string;
  icon?: Parameters<typeof Icon>[0]["name"];
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="card">
      <div className="card-head" onClick={() => setOpen((o) => !o)}>
        <div className="card-head-title">
          <Icon name={icon} />
          {title}
        </div>
        <Icon name="chevron" className={`icon chev${open ? " open" : ""}`} />
      </div>
      {open && <div className="card-body">{children}</div>}
    </div>
  );
}
