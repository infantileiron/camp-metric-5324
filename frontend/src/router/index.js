export const routes=['口径目录','事实校验','口径试算','签核历史','滚动监测'];export const page=()=>Math.min(routes.length-1,Math.max(0,Number(location.hash.slice(1)||0)));
