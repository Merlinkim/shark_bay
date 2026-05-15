import { Award, BadgeCheck, BriefcaseBusiness, Building2, Coins, Gem, HeartHandshake, ShieldCheck, Sparkles, Wallet } from 'lucide-react';

const trustCards = [
  { title: '프라임에셋 부지점장', icon: Gem },
  { title: '1000+ 상담 및 보상 경험', icon: BadgeCheck },
  { title: '2024~2025 300 CLUB', icon: Award },
  { title: '법무/세무/손해사정 제휴', icon: BriefcaseBusiness },
];

const solutionCards = [
  { title: '보험료 절감', body: '중복되거나 불필요한 특약을 분석하여 보험료 부담을 줄입니다.', icon: Wallet },
  { title: '중복 보장 정리', body: '여러 보험사에 흩어진 보장을 정리하고 핵심 보장을 유지합니다.', icon: ShieldCheck },
  { title: '부족한 보장 분석', body: '실제 필요한 위험 대비 부족한 보장을 확인하고 보완합니다.', icon: HeartHandshake },
  { title: '법인 절세 전략', body: '법인 운영 구조와 절세 목적에 맞춘 보험 전략을 설계합니다.', icon: Building2 },
  { title: '상속/증여 설계', body: '가족 자산 이전 과정에서 발생할 수 있는 리스크를 대비합니다.', icon: Coins },
];

export function DashboardPage() {
  return (
    <div className="pb-28 sm:pb-32">
      <section className="relative overflow-hidden rounded-[26px] border border-[#2f323c] bg-[#090c13] px-5 pb-8 pt-7 shadow-[0_24px_65px_rgba(0,0,0,0.58)] sm:px-8 sm:pt-10">
        <div className="pointer-events-none absolute -right-28 top-24 h-56 w-56 rounded-full bg-[#d9b678]/15 blur-3xl" />
        <div className="pointer-events-none absolute -left-20 -top-20 h-52 w-52 rounded-full bg-[#153260]/30 blur-3xl" />

        <div className="relative mx-auto max-w-6xl">
          <div className="grid items-center gap-7 lg:grid-cols-[1.08fr_0.92fr] lg:gap-10">
            <div className="motion-fade-up space-y-5">
              <p className="inline-flex items-center gap-2 rounded-full border border-[#b99758]/45 bg-[#121722]/90 px-3 py-1 text-[11px] font-semibold tracking-[0.16em] text-[#d8bc82]">PRIVATE INSURANCE ADVISORY</p>
              <h1 className="text-[1.86rem] font-semibold leading-[1.25] tracking-[-0.02em] text-[#f8fbff] sm:text-[2.48rem] sm:leading-[1.2]">보험은 가입보다 <span className="text-[#dfc68d]">구조 설계</span>가 중요합니다.</h1>
              <p className="max-w-xl text-[15px] leading-7 text-[#c0c9d9] sm:text-[17px]">보험료 낭비를 줄이고, 필요한 보장을 정확히 맞추는 프리미엄 컨설팅. 개인·가족·법인 재무 목표까지 고려한 전략으로 설계해드립니다.</p>
              <div className="flex flex-wrap items-center gap-2.5">
                {['1:1 맞춤 진단', '계약 분석 리포트', '법무·세무 연계'].map((badge) => (
                  <span key={badge} className="rounded-full border border-[#3a404d] bg-[#111723] px-3 py-1.5 text-xs font-medium text-[#d4dbe7]">{badge}</span>
                ))}
              </div>
              <div className="flex flex-wrap items-center gap-2.5">
                <button className="premium-button min-h-12 rounded-xl px-5 text-sm font-semibold sm:text-[15px]">무료 보장 점검 신청</button>
                <button className="min-h-12 rounded-xl border border-[#3d4351] bg-[#131925] px-5 text-sm font-semibold text-[#dde5f1] transition duration-300 hover:border-[#697488] hover:bg-[#1a2232]">카카오 상담 문의</button>
              </div>
            </div>

            <div className="motion-fade-up relative" style={{ animationDelay: '120ms' }}>
              <div className="absolute -inset-4 rounded-[28px] bg-[#d5b374]/15 blur-2xl" />
              <div className="relative rounded-[24px] border border-[#394054] bg-gradient-to-b from-[#131b2c] to-[#101722] p-4 shadow-[0_30px_65px_rgba(0,0,0,0.5)] sm:p-5">
                <img
                  src="https://images.unsplash.com/photo-1551836022-d5d88e9218df?auto=format&fit=crop&w=1200&q=80"
                  alt="보험 포트폴리오 상담"
                  className="h-[260px] w-full rounded-2xl object-cover sm:h-[330px]"
                />
                <div className="mt-4 grid grid-cols-2 gap-2.5">
                  <div className="rounded-xl bg-[#111723] p-3">
                    <p className="text-[11px] text-[#95a2b8]">상담 만족도</p>
                    <p className="mt-1 text-base font-semibold text-[#f2f6ff]">4.9 / 5.0</p>
                  </div>
                  <div className="rounded-xl bg-[#111723] p-3">
                    <p className="text-[11px] text-[#95a2b8]">연 평균 점검 건수</p>
                    <p className="mt-1 text-base font-semibold text-[#f2f6ff]">300+ 건</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="mt-8 space-y-4 sm:mt-10">
        <h2 className="text-xl font-semibold tracking-[-0.01em] text-[#f4f8ff] sm:text-[1.6rem]">신뢰를 증명하는 이력</h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {trustCards.map(({ title, icon: Icon }, index) => (
            <article key={title} className="motion-fade-up premium-card group rounded-2xl border border-[#313845] bg-[#f8fafc] p-4 text-[#141927]" style={{ animationDelay: `${index * 70}ms` }}>
              <div className="mb-4 flex items-center gap-3">
                <span className="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-[#0f1d35] text-[#debf85]"><Icon size={19} /></span>
                <span className="h-[2px] flex-1 rounded-full bg-gradient-to-r from-[#d8bb7f] to-transparent" />
              </div>
              <h3 className="text-[15px] font-semibold leading-6">{title}</h3>
            </article>
          ))}
        </div>
      </section>

      <section className="mt-8 space-y-4 sm:mt-10">
        <h2 className="text-xl font-semibold tracking-[-0.01em] text-[#f4f8ff] sm:text-[1.6rem]">보험 구조, 이렇게 바꿉니다</h2>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {solutionCards.map(({ title, body, icon: Icon }, index) => (
            <article key={title} className="motion-fade-up rounded-2xl border border-[#2f3544] bg-[#101620] p-4 shadow-[0_18px_38px_rgba(0,0,0,0.35)] transition duration-300 hover:-translate-y-0.5 hover:border-[#4c5569]" style={{ animationDelay: `${index * 65}ms` }}>
              <div className="mb-2.5 flex items-center gap-2.5">
                <span className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-[#d8bb7f]/20 text-[#dfc283]"><Icon size={18} /></span>
                <h3 className="text-[16px] font-semibold text-[#f2f7ff]">{title}</h3>
              </div>
              <p className="text-[14px] leading-6 text-[#b6c0d2]">{body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="mt-8 rounded-2xl border border-[#2f3540] bg-gradient-to-br from-[#0f1522] to-[#0b111b] p-5 shadow-[0_22px_55px_rgba(0,0,0,0.46)] sm:mt-10 sm:p-7">
        <div className="flex items-start gap-3">
          <Sparkles className="mt-1 text-[#e0c183]" size={18} />
          <div>
            <h3 className="text-lg font-semibold text-[#f8fbff]">첫 상담에서 바로 계약을 권하지 않습니다.</h3>
            <p className="mt-2 text-[14px] leading-6 text-[#bdc8db]">현재 보장 포트폴리오를 먼저 구조적으로 분석하고, 절감/보완 포인트를 수치로 안내합니다. 고객의 재무 목표에 맞지 않으면 가입을 권하지 않습니다.</p>
          </div>
        </div>
      </section>

      <div className="fixed inset-x-0 bottom-3 z-50 px-4 sm:bottom-5">
        <div className="mx-auto flex max-w-3xl items-center gap-2.5 rounded-2xl border border-[#3a404e] bg-[#0d121bdd]/95 p-2.5 shadow-[0_18px_45px_rgba(0,0,0,0.5)] backdrop-blur-md">
          <button className="min-h-12 flex-1 rounded-xl border border-[#474f60] bg-[#151b27] px-4 text-sm font-semibold text-[#e4ebf7]">전화 상담 예약</button>
          <button className="premium-button min-h-12 flex-[1.3] rounded-xl px-4 text-sm font-semibold">카카오로 1분 상담 시작</button>
        </div>
      </div>
    </div>
  );
}
