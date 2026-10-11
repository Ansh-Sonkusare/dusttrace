export default function NoRun() {
  return (
    <div className="panel empty">
      <p><b>No forecast run yet.</b></p>
      <p className="small">Run the engine to fill this console: <code>python -m dusttrace all</code> from <code>services/engine</code>.</p>
    </div>
  );
}
