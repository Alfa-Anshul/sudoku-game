import React, { useState, useEffect, useCallback } from 'react';
import { generateFullBoard, createPuzzle, isValid, getHint, TIPS } from './sudoku';
import './App.css';

const DIFF = { Easy:42, Medium:32, Hard:24 };

export default function App() {
  const [diff, setDiff] = useState('Medium');
  const [solution, setSolution] = useState(null);
  const [board, setBoard] = useState(null);
  const [locked, setLocked] = useState({});
  const [sel, setSel] = useState(null);
  const [errors, setErrors] = useState({});
  const [hinted, setHinted] = useState({});
  const [won, setWon] = useState(false);
  const [timer, setTimer] = useState(0);
  const [running, setRunning] = useState(false);
  const [notes, setNotes] = useState({});
  const [noteMode, setNoteMode] = useState(false);
  const [hintCount, setHintCount] = useState(0);
  const [tipIdx, setTipIdx] = useState(0);
  const [history, setHistory] = useState([]);
  const [shake, setShake] = useState(null);

  const startGame = useCallback((d) => {
    const full = generateFullBoard();
    const puz = createPuzzle(full, DIFF[d]);
    const lk = {};
    for(let r=0;r<9;r++) for(let c=0;c<9;c++) if(puz[r][c]!==0) lk[`${r}-${c}`]=true;
    setSolution(full); setBoard(puz.map(r=>[...r])); setLocked(lk);
    setSel(null); setErrors({}); setHinted({}); setWon(false);
    setTimer(0); setRunning(true); setNotes({}); setNoteMode(false);
    setHintCount(0); setHistory([]); setTipIdx(Math.floor(Math.random()*TIPS.length));
  }, []);

  useEffect(() => { startGame('Medium'); }, []);

  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => setTimer(t => t+1), 1000);
    return () => clearInterval(id);
  }, [running]);

  const fmt = s => `${String(Math.floor(s/60)).padStart(2,'0')}:${String(s%60).padStart(2,'0')}`;

  const input = (num) => {
    if (!sel || won) return;
    const [r,c] = sel;
    if (locked[`${r}-${c}`]) return;
    if (noteMode && num!==0) {
      setNotes(prev => {
        const cur = new Set(prev[`${r}-${c}`]||[]);
        cur.has(num)?cur.delete(num):cur.add(num);
        return {...prev,[`${r}-${c}`]:cur};
      }); return;
    }
    setHistory(h=>[...h,{board:board.map(r=>[...r]),errors:{...errors},notes:{...notes}}]);
    const nb = board.map(row=>[...row]);
    nb[r][c] = num===nb[r][c]?0:num;
    const ne = {...errors}; delete ne[`${r}-${c}`];
    if (num!==0 && solution && nb[r][c]!==solution[r][c]) {
      ne[`${r}-${c}`]=true; setShake(`${r}-${c}`);
      setTimeout(()=>setShake(null),420);
    }
    setBoard(nb); setErrors(ne);
    setNotes(prev=>{const n={...prev};delete n[`${r}-${c}`];return n;});
    if (solution && nb.every((row,ri)=>row.every((v,ci)=>v!==0&&v===solution[ri][ci])))
      { setWon(true); setRunning(false); }
  };

  const undo = () => {
    if (!history.length) return;
    const last = history[history.length-1];
    setBoard(last.board); setErrors(last.errors); setNotes(last.notes);
    setHistory(h=>h.slice(0,-1));
  };

  const hint = () => {
    if (!solution||won) return;
    const h = getHint(board,solution); if(!h) return;
    setHistory(prev=>[...prev,{board:board.map(r=>[...r]),errors:{...errors},notes:{...notes}}]);
    setHintCount(hc=>hc+1);
    const nb = board.map(r=>[...r]); nb[h.row][h.col]=h.value;
    setBoard(nb); setHinted(prev=>({...prev,[`${h.row}-${h.col}`]:true}));
    setSel([h.row,h.col]);
    setErrors(prev=>{const e={...prev};delete e[`${h.row}-${h.col}`];return e;});
    setNotes(prev=>{const n={...prev};delete n[`${h.row}-${h.col}`];return n;});
    if (nb.every((row,ri)=>row.every((v,ci)=>v!==0&&v===solution[ri][ci])))
      { setWon(true); setRunning(false); }
  };

  const highlight = (r,c) => {
    if (!sel) return false;
    const [sr,sc]=sel;
    return r===sr||c===sc||(Math.floor(r/3)===Math.floor(sr/3)&&Math.floor(c/3)===Math.floor(sc/3));
  };
  const sameVal = (r,c) => {
    if (!sel||!board) return false;
    const sv=board[sel[0]][sel[1]];
    return sv!==0&&board[r][c]===sv;
  };
  const numCount = n => board?board.flat().filter(v=>v===n).length:0;

  if (!board) return <div className="loading"><div className="spinner"/><span>Generating…</span></div>;

  const filled=board.flat().filter(v=>v!==0).length;
  const pct=Math.round((filled/81)*100);
  const tip=TIPS[tipIdx%TIPS.length];

  return (
    <div className="app">
      <div className="canvas"><div className="o o1"/><div className="o o2"/><div className="o o3"/><div className="grid-bg"/></div>

      <header className="hdr">
        <div className="logo"><span className="ls">✦</span><span className="lt">SUDOKU</span></div>
        <div className="chips">
          <div className="chip"><span>⏱</span><span className="cv">{fmt(timer)}</span></div>
          <div className="chip"><span>💡</span><span className="cv">{hintCount} hints</span></div>
        </div>
      </header>

      <div className="tbar">
        <div className="dgrp">
          {Object.keys(DIFF).map(d=>(
            <button key={d} className={`dbtn${diff===d?' on':''}`}
              onClick={()=>{setDiff(d);startGame(d);}}>{d}</button>
          ))}
        </div>
        <button className="nbtn" onClick={()=>startGame(diff)}>⟳ New Game</button>
      </div>

      <div className="layout">
        <div className="bwrap">
          {won&&(
            <div className="wov">
              <div className="wcard">
                <div className="crow">{['🎉','✨','🏆','✨','🎉'].map((e,i)=><span key={i} style={{animationDelay:`${i*.1}s`}}>{e}</span>)}</div>
                <h2 className="wtitle">Brilliant!</h2>
                <p className="wsub">Solved in <b>{fmt(timer)}</b> · <b>{hintCount}</b> hint{hintCount!==1?'s':''}</p>
                <div className="wrate">{hintCount===0?'⭐⭐⭐ Perfect solve!':hintCount<=3?'⭐⭐ Great job!':'⭐ Well done!'}</div>
                <button className="nbtn" onClick={()=>startGame(diff)}>Play Again</button>
              </div>
            </div>
          )}
          <div className="board">
            {board.map((row,r)=>row.map((val,c)=>{
              const k=`${r}-${c}`;
              const isLock=locked[k],isSel=sel&&sel[0]===r&&sel[1]===c;
              const cn=[
                'cell',isLock?'lk':'ed',
                isSel?'sl':'',
                !isSel&&highlight(r,c)?'hl':'',
                !isSel&&sameVal(r,c)?'sv':'',
                errors[k]?'er':'',hinted[k]?'hi':'',
                shake===k?'sk':'',
                c===2||c===5?'br':'',r===2||r===5?'bb':''
              ].filter(Boolean).join(' ');
              const cn2=notes[k];
              return (
                <div key={k} className={cn} onClick={()=>{if(!won)setSel([r,c]);}}>
                  {val!==0?(<span className="cv2">{val}</span>)
                    :cn2&&cn2.size>0?(
                      <div className="ng">
                        {[1,2,3,4,5,6,7,8,9].map(n=>(
                          <span key={n} className={`nt${cn2.has(n)?' on':''}`}>{n}</span>
                        ))}
                      </div>
                    ):null}
                </div>
              );
            }))}
          </div>
        </div>

        <div className="side">
          <div className="slabel">Numbers</div>
          <div className="npad">
            {[1,2,3,4,5,6,7,8,9].map(n=>{
              const cnt=numCount(n);
              return (
                <button key={n} className={`nk${cnt>=9?' done':''}`}
                  onClick={()=>input(n)} disabled={cnt>=9}>
                  <span className="nn">{n}</span>
                  <span className="nc">{cnt}/9</span>
                </button>
              );
            })}
            <button className="nk ek" onClick={()=>input(0)}>⌫</button>
          </div>

          <div className="acts">
            <button className={`ab${noteMode?' an':''}`} onClick={()=>setNoteMode(m=>!m)}>
              <span>✏️</span><span>{noteMode?'Notes ON':'Notes'}</span>
            </button>
            <button className="ab" onClick={undo} disabled={!history.length}>
              <span>↩</span><span>Undo</span>
            </button>
            <button className="ab hb" onClick={hint}>
              <span>💡</span><span>Hint</span>
            </button>
          </div>

          <div className="pcard">
            <div className="ph"><span>Progress</span><span className="pv">{pct}%</span></div>
            <div className="pt"><div className="pf" style={{width:`${pct}%`}}/></div>
            <div className="pc"><span>{filled} filled</span><span>{81-filled} left</span></div>
          </div>

          <div className="tcard">
            <div className="tbadge">💬 Strategy Tip</div>
            <div className="ttitle">{tip.title}</div>
            <div className="tbody">{tip.body}</div>
            <button className="tnext" onClick={()=>setTipIdx(i=>(i+1)%TIPS.length)}>Next tip →</button>
          </div>
        </div>
      </div>
    </div>
  );
}
