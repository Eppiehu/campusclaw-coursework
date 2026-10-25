<script setup lang="ts">
import {onMounted,onBeforeUnmount,ref,watch} from 'vue'
import * as echarts from 'echarts/core'
import {BarChart} from 'echarts/charts'
import {GridComponent,TooltipComponent} from 'echarts/components'
import {CanvasRenderer} from 'echarts/renderers'
echarts.use([BarChart,GridComponent,TooltipComponent,CanvasRenderer])
const props=defineProps<{facts:any}>();const host=ref<HTMLElement>();let chart:echarts.ECharts | undefined
function draw(){chart?.setOption({color:['#147d73'],tooltip:{},grid:{top:20,bottom:30,left:36,right:12},xAxis:{type:'category',data:['60分以下','60–79分','80分及以上']},yAxis:{type:'value',minInterval:1},series:[{type:'bar',barWidth:40,data:[props.facts.score_distribution?.below_60||0,props.facts.score_distribution?.['60_to_79']||0,props.facts.score_distribution?.['80_plus']||0]}]})}
const resize=()=>chart?.resize()
onMounted(()=>{chart=echarts.init(host.value!);draw();window.addEventListener('resize',resize)})
watch(()=>props.facts,draw,{deep:true});onBeforeUnmount(()=>{window.removeEventListener('resize',resize);chart?.dispose()})
</script>
<template><div ref="host" class="score-chart" aria-label="本周成绩分布图"></div></template>
