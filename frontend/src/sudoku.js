export function generateFullBoard() {
  const board = Array.from({ length: 9 }, () => Array(9).fill(0));
  fillBoard(board);
  return board;
}
function fillBoard(board) {
  for (let r = 0; r < 9; r++) {
    for (let c = 0; c < 9; c++) {
      if (board[r][c] === 0) {
        const nums = [1,2,3,4,5,6,7,8,9].sort(() => Math.random() - 0.5);
        for (let n of nums) {
          if (isSafe(board, r, c, n)) {
            board[r][c] = n;
            if (fillBoard(board)) return true;
            board[r][c] = 0;
          }
        }
        return false;
      }
    }
  }
  return true;
}
function isSafe(board, row, col, num) {
  for (let i = 0; i < 9; i++) {
    if (board[row][i] === num || board[i][col] === num) return false;
  }
  const br = Math.floor(row/3)*3, bc = Math.floor(col/3)*3;
  for (let r = br; r < br+3; r++)
    for (let c = bc; c < bc+3; c++)
      if (board[r][c] === num) return false;
  return true;
}
export function isValid(board, row, col, num) { return isSafe(board, row, col, num); }
export function createPuzzle(full, clues=35) {
  const puzzle = full.map(r=>[...r]);
  const cells = [];
  for (let r=0;r<9;r++) for(let c=0;c<9;c++) cells.push([r,c]);
  cells.sort(()=>Math.random()-0.5);
  let removed=0;
  for (const [r,c] of cells) {
    if (removed>=81-clues) break;
    puzzle[r][c]=0; removed++;
  }
  return puzzle;
}
export function getHint(board, solution) {
  const empties=[];
  for(let r=0;r<9;r++) for(let c=0;c<9;c++) if(board[r][c]===0) empties.push([r,c]);
  if(!empties.length) return null;
  const [r,c]=empties[Math.floor(Math.random()*empties.length)];
  return {row:r,col:c,value:solution[r][c]};
}
export const TIPS = [
  {title:'Lone Singles', body:'If a cell has only one possible number, that must be the answer. Check every empty cell first!'},
  {title:'Hidden Singles', body:'If a number can only go in one cell within a row, column, or box — place it there, even if other candidates exist.'},
  {title:'Box Elimination', body:'Once a number is placed in a box, remove it as a candidate from all other cells in that box instantly.'},
  {title:'Naked Pairs', body:'If two cells in the same group share the same two candidates only, eliminate those from all other cells in the group.'},
  {title:'Pointing Pairs', body:'If a number in a box can only appear in one row/column, eliminate it from the rest of that row/column outside the box.'},
  {title:'Cross-Hatch Scan', body:'Pick a number. Where it already appears in rows and columns, cross those off — remaining cells narrow it down fast.'},
  {title:'Start Constrained', body:'Rows, columns, or boxes with 7+ filled cells have almost no choices. Solve those first for quick wins.'},
  {title:'Use Pencil Marks', body:'Turn on Notes mode and pencil in all candidates. Then eliminate systematically as you fill in numbers.'},
  {title:'Work the Boxes', body:'Boxes with more filled cells give you more constraints. Tackle densely-filled boxes before open rows or columns.'},
  {title:'Count Rare Numbers', body:'Find which numbers appear fewest times on the board — they have fewer possible locations and are easiest to place.'}
];
