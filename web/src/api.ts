export const base='/api/nexus'
export const token=()=>localStorage.getItem('nexus-token') || ''
export async function api(path:string,method='GET',body?:unknown):Promise<any>{
  const form=body instanceof FormData
  const response=await fetch(base+path,{method,credentials:'omit',headers:{Authorization:'Bearer '+token(),...(!form&&body!==undefined?{'Content-Type':'application/json'}:{})},body:body===undefined?undefined:form?body:JSON.stringify(body)})
  const value=await response.json().catch(()=>({error:'服务暂时不可用'}))
  if(!response.ok)throw new Error(value.error || '请求失败')
  return value
}
export async function download(id:number){
  const response=await fetch(base+`/materials/${id}/download`,{headers:{Authorization:'Bearer '+token()},credentials:'omit'})
  if(!response.ok)throw new Error('下载失败或无权访问')
  const url=URL.createObjectURL(await response.blob());const a=document.createElement('a');a.href=url;a.download=`讲义-${id}.txt`;a.click();URL.revokeObjectURL(url)
}
