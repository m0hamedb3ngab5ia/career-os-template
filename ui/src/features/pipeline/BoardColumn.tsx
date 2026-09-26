import { useVirtualizer } from "@tanstack/react-virtual";
import { useRef, useState, type DragEvent, type ReactNode } from "react";
import { formatCount } from "../../lib/format";
import styles from "./Pipeline.module.css";
import type { Card, Column } from "./types";

/** Past this many cards an expanded column renders only what is on screen (Pipeline › Found can hold thousands). */
export const VIRTUALIZE_AT = 60;

interface BoardColumnProps {
  column: Column;
  expanded: boolean;
  onToggleExpand: () => void;
  /** Accepts a drop while a card from another column is dragged. */
  canDrop: boolean;
  onDropCard: () => void;
  renderCard: (card: Card) => ReactNode;
}

function VirtualCards({ cards, renderCard }: { cards: Card[]; renderCard: (c: Card) => ReactNode }) {
  const scroller = useRef<HTMLDivElement>(null);
  const v = useVirtualizer({ count: cards.length, getScrollElement: () => scroller.current, estimateSize: () => 132, gap: 8, overscan: 6 });
  return (
    <div ref={scroller} className={styles.scroller}>
      <ul className={styles.cards} style={{ height: v.getTotalSize(), position: "relative", display: "block" }}>
        {v.getVirtualItems().map((row) => (
          <li
            key={cards[row.index]!.job_id}
            ref={v.measureElement}
            data-index={row.index}
            style={{ position: "absolute", top: 0, left: 0, right: 0, transform: `translateY(${row.start}px)` }}
          >
            {renderCard(cards[row.index]!)}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function BoardColumn({ column, expanded, onToggleExpand, canDrop, onDropCard, renderCard }: BoardColumnProps) {
  const [over, setOver] = useState(false);
  const id = `col-${column.name.replace(/\W+/g, "-").toLowerCase()}`;
  const hidden = column.count - column.cards.length;

  function onDragOver(e: DragEvent) {
    if (!canDrop) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    if (!over) setOver(true);
  }

  return (
    <section
      aria-labelledby={id}
      className={styles.column}
      data-drop={(canDrop && over) || undefined}
      onDragOver={onDragOver}
      onDragLeave={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setOver(false);
      }}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        if (canDrop) onDropCard();
      }}
    >
      <h2 id={id} className={styles.columnTitle}>
        {column.name}{" "}
        <span className={styles.count}>
          {formatCount(column.count)} <span className="sr-only">jobs</span>
        </span>
      </h2>
      {column.cards.length === 0 ? (
        <div className={styles.emptyColumn}>No jobs here yet</div>
      ) : column.cards.length > VIRTUALIZE_AT ? (
        <VirtualCards cards={column.cards} renderCard={renderCard} />
      ) : (
        <ul className={styles.cards}>
          {column.cards.map((c) => (
            <li key={c.job_id}>{renderCard(c)}</li>
          ))}
        </ul>
      )}
      {hidden > 0 ? (
        <button type="button" className={styles.showAll} aria-expanded={false} onClick={onToggleExpand}>
          Show all {formatCount(column.count)} <span className="sr-only">{column.name} jobs</span>
        </button>
      ) : expanded ? (
        <button type="button" className={styles.showAll} aria-expanded onClick={onToggleExpand}>
          Show fewer <span className="sr-only">{column.name} jobs</span>
        </button>
      ) : null}
    </section>
  );
}
