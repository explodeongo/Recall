/** The "R" mark, for generated icons. `padding` leaves the safe zone maskable icons need. */
export function Mark({ size, padding = 0, radius = 0.22 }: { size: number; padding?: number; radius?: number }) {
  const inner = size - padding * 2;
  return (
    <div style={{ width: size, height: size, display: "flex", alignItems: "center", justifyContent: "center", background: "#4f46c8" }}>
      <div
        style={{
          width: inner,
          height: inner,
          borderRadius: inner * radius,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "white",
          fontSize: inner * 0.62,
          fontWeight: 700,
          fontFamily: "Georgia, serif",
        }}
      >
        R
      </div>
    </div>
  );
}
