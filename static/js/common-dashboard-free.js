'use strict'

window.addEventListener('load', () => {
  ;(function () {
    // Revenue Goal Radial Chart
    buildChart('#revenue-chart', () => ({
      chart: {
        height: 182,
        width: 182,
        type: 'donut',
        offsetX: 10,
        parentHeightOffset: 0
      },
      labels: ['Discount', 'Profit', 'Sale'],
      series: [14987, 1735, 11548],
      colors: ['var(--color-primary)', 'var(--color-success)', 'var(--color-warning)'],
      stroke: {
        width: 4,
        colors: ['var(--color-base-200)']
      },
      dataLabels: {
        enabled: false
      },
      legend: {
        show: false
      },
      grid: {
        show: false
      },
      states: {
        hover: {
          filter: { type: 'none' }
        },
        active: {
          filter: { type: 'none' }
        }
      },
      plotOptions: {
        pie: {
          expandOnClick: false,

          donut: {
            size: '83%',
            background: 'transparent',
            labels: {
              show: true,
              value: {
                fontSize: '1.5rem',
                fontFamily: 'Inter, ui-sans-serif',
                fontWeight: 700,
                color: 'var(--color-base-content)',
                offsetY: -17,
                formatter: function (val) {
                  return '$' + parseInt(val)
                }
              },
              name: {
                offsetY: 17,
                fontFamily: 'Inter, ui-sans-serif'
              },
              total: {
                show: true,
                fontSize: '14px',
                color: 'var(--color-base-content)',
                fontWeight: 500,
                label: 'Total Profit',
                formatter: function (w) {
                  return '$1735'
                }
              }
            }
          }
        }
      }
    }))
  })()
})
