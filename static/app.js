async function calculateCredit(price, carId) {
  const down = Number(document.getElementById('down').value || 0);
  const months = Number(document.getElementById('months').value || 0);
  const rate = Number(document.getElementById('rate').value || 0);
  const result = document.getElementById('credit-result');
  if (down < 0 || down >= price || months < 1 || months > 360 || rate < 0 || rate > 100) {
    result.textContent = 'Проверьте сумму взноса, срок и ставку.'; return;
  }
  result.textContent = 'Выполняется расчёт...';
  try {
    const response = await fetch('/credit/calculate', {method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({amount:price-down,months,rate,car_id:carId})});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Ошибка расчёта');
    result.innerHTML = `<b>${data.monthly_payment.toLocaleString('ru-RU')} ₽ / мес.</b><span>Общая сумма выплат: ${data.total.toLocaleString('ru-RU')} ₽</span><small>${data.source}</small>`;
  } catch(e) { result.textContent = e.message; }
}
document.addEventListener('DOMContentLoaded',()=>{
  document.querySelectorAll('.flash').forEach(el=>setTimeout(()=>el.classList.add('fade'),5000));
});
