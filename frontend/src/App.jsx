import React, { useState, useEffect, useCallback } from 'react';
import { generateFullBoard, createPuzzle, isValid, getHint, getTip } from './sudoku';
import './App.css';

const DIFFICULTIES = { Easy: 40, Medium: 32, Hard: 25 };

export default function App() {
  const [difficulty, setDifficulty] = useState('Medium');
  const [solution, setSolution] = useState(null);
  const [board, setBoard] = useState(null);
  const [locked, setLocked] = useState({});
  const [selected, setSelected] = useState(null);
  const [errors, setErrors] = useState({});
  const [hint, setHint] = useState(null);
  const [tip, setTip] = useState('');
  const [won, setWon] = useState(false);
  const [timer, setTimer] = useState(0);
  const [running, setRunning] = useState(false);
  const [notes, setNotes] = useState({});
  const [noteMode, setNoteMode] = useState(false);
  const [hintCount, setHintCount] = useState(0);

  const newGame = useCallback((diff) => {
    const d = diff || difficulty;
    const full = generateFullBoard();
    const puz = createPuzzle(full, DIFFICULTIES[d]);
    const lk = {};
    for (let r = 0; r < 9; r++)
      for (let c = 0; c < 9; c++)
        if (puz[r][c] !== 0) lk[`${r}-${c}`] = true;
    setSolution(full);
    setBoard(puz.map(r => [...r]));
    setLocked(lk);
    setSelected(null);
    setErrors({});
    setHint(null);
    setTip(getTip());
    setWon(false);
    setTimer(0);
    setRunning(true);
    setNotes({});
    setHintCount(0);
  }, [difficulty]);

  useEffect(() => { newGame(); }, []);

  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => setTimer(t => t + 1), 1000);
    return () => clearInterval(id);
  }, [running]);

  const fmt = s => `${String(Math.floor(s/60)).padStart(2,'0')}:${String(s%60).padStart(2,'0')}`;

  const handleCell = (r, c) => { if (!won) { setSelected([r, c]); setHint(null); } };

  const handleInput = (num) => {
    if (!selected || won) return;
    const [r, c] = selected;
    if (locked[`${r}-${c}`]) return;
    if (noteMode) {
      const key = `${r}-${c}`;
      setNotes(prev => {
        const cur = new Set(prev[key] || []);
        cur.has(num) ? cur.delete(num) : cur.add(num);
        return { ...prev, [key]: cur };
      });
      return;
    }
    const nb = board.map(row => [...row]);
    nb[r][c] = num === nb[r][c] ? 0 : num;
    const ne = { ...errors };
    delete ne[`${r}-${c}`];
    if (num !== 0 && !isValid(nb, r, c, num)) ne[`${r}-${c}`] = true;
    setBoard(nb);
    setErrors(ne);
    setNotes(prev => { const n = {...prev}; delete n[`${r}-${c}`]; return n; });
    const complete = nb.every((row, ri) => row.every((v, ci) => v !== 0 && v === solution[ri][ci]));
    if (complete) { setWon(true); setRunning(false); }
  };

  const handleHint = () => {
    if (!solution || won) return;
    const h = getHint(board, solution);
    if (!h) return;
    setHint(h);
    setHintCount(hc => hc + 1);
    const nb = board.map(r => [...r]);
    nb[h.row][h.col] = h.value;
    setBoard(nb);
    setSelected([h.row, h.col]);
    setErrors(prev => { const e = {...prev}; delete e[`${h.row}-${h.col}`]; return e; });
    const complete = nb.every((row, ri) => row.every((v, ci) => v !== 0 && v === solution[ri][ci]));
    if (complete) { setWon(true); setRunning(false); }
  };

  const isHighlighted = (r, c) => {
    if (!selected) return false;
    const [sr, sc] = selected;
    return r === sr || c === sc || (Math.floor(r/3) === Math.floor(sr/3) && Math.floor(c/3) === Math.floor(sc/3));
  };

  const isSameVal = (r, c) => {
    if (!selected || !board) return false;
    const sv = board[selected[0]][selected[1]];
    return sv !== 0 && board[r][c] === sv;
  };

  if (!board) return <div className="loading">Generating puzzle…</div>;

  const filled = board.flat().filter(v => v !== 0).length;
  const pct = Math.round((filled / 81) * 100);

  return (
    <div className="app">
      <div className="bg-decor">
        <div className="blob blob1" /><div className="blob blob2" /><div className="blob blob3" />
      </div>
      <header className="header">
        <div className="logo">✦ SUDOKU</div>
        <div className="header-right">
          <span className="timer">{fmt(timer)}</span>
          <span className="hints-badge">💡 {hintCount} hints</span>
        </div>
      </header>
      <div className="controls-row">
        {Object.keys(DIFFICULTIES).map(d => (
          <button key={d} className={`diff-btn ${difficulty === d ? 'active' : ''}`}
            onClick={() => { setDifficulty(d); newGame(d); }}>{d}</button>
        ))}
        <button className="new-game-btn" onClick={() => newGame()}>New Game</button>
      </div>
      <div className="game-area">
        <div className="board-wrap">
          {won && (
            <div className="win-overlay">
              <div className="win-card">
                <div className="win-emoji">🎉</div>
                <div className="win-title">Brilliant!</div>
                <div className="win-sub">Solved in {fmt(timer)} · {hintCount} hint{hintCount !== 1 ? 's' : ''} used</div>
                <button className="new-game-btn" onClick={() => newGame()}>Play Again</button>
              </div>
            </div>
          )}
          <div className="board">
            {board.map((row, r) => row.map((val, c) => {
              const key = `${r}-${c}`;
              const isLocked = locked[key];
              const isSelected = selected && selected[0] === r && selected[1] === c;
              const isErr = errors[key];
              const isHinted = hint && hint.row === r && hint.col === c;
              const cellNotes = notes[key];
              return (
                <div key={key}
                  className={['cell', isLocked?'locked':'', isSelected?'selected':'',
                    isHighlighted(r,c)&&!isSelected?'highlighted':'',
                    isSameVal(r,c)?'same-val':'', isErr?'error':'', isHinted?'hinted':'',
                    c===2||c===5?'border-right':'', r===2||r===5?'border-bottom':''
                  ].filter(Boolean).join(' ')}
                  onClick={() => handleCell(r, c)}>
                  {val !== 0 ? (
                    <span className="cell-num">{val}</span>
                  ) : cellNotes && cellNotes.size > 0 ? (
                    <div className="notes-grid">
                      {[1,2,3,4,5,6,7,8,9].map(n => (
                        <span key={n} className={`note-num ${cellNotes.has(n)?'visible':''}`}>{n}</span>
                      ))}
                    </div>
                  ) : null}
                </div>
              );
            }))}
          </div>
        </div>
        <div className="side-panel">
          <div className="numpad">
            {[1,2,3,4,5,6,7,8,9].map(n => (
              <button key={n} className="num-btn" onClick={() => handleInput(n)}>{n}</button>
            ))}
            <button className="num-btn erase" onClick={() => handleInput(0)}>✕</button>
          </div>
          <div className="action-btns">
            <button className={`action-btn ${noteMode?'note-active':''}`} onClick={() => setNoteMode(m=>!m)}>
              ✏️ {noteMode?'Notes ON':'Notes'}
            </button>
            <button className="action-btn hint-btn" onClick={handleHint}>💡 Hint</button>
          </div>
          <div className="tip-card">
            <div className="tip-header">💬 Strategy Tip</div>
            <div className="tip-body">{tip}</div>
            <button className="tip-refresh" onClick={() => setTip(getTip())}>Next tip →</button>
          </div>
          <div className="progress-card">
            <div className="progress-label">Progress</div>
            <div className="progress-bar-wrap"><div className="progress-bar" style={{width:`${pct}%`}} /></div>
            <div className="progress-pct">{pct}% filled</div>
          </div>
        </div>
      </div>
    </div>
  );
}
