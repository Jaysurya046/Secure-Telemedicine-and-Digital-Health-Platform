'use client';

import React, { useEffect, useState, useRef } from 'react';
import type { FormEvent } from 'react';
import {
  CalendarPlus,
  Calendar,
  Clock,
  AlertCircle,
  CheckCircle2,
  RefreshCw,
  ChevronLeft,
  ChevronRight,
  Info,
  Stethoscope,
  X
} from 'lucide-react';
import { AppNav } from '@/components/AppNav';
import { apiFetch, toIsoTimestamp, isInvalidPageError } from '@/lib/api';

const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

type Doctor = {
  id: string;
  email: string;
  profile?: {
    first_name?: string;
    last_name?: string;
    full_name?: string;
  };
  doctor_profile?: {
    specialty?: string;
  };
};

type Availability = {
  id: string;
  doctor: string;
  weekday: number;
  start_time: string;
  end_time: string;
  is_active: boolean;
};

type Appointment = {
  id: string;
  doctor: string;
  patient: string;
  doctor_detail?: Doctor;
  scheduled_start: string;
  scheduled_end: string;
  status: 'pending' | 'confirmed' | 'cancelled' | 'completed' | 'no_show';
  reason: string;
  symptoms?: string[];
  notes?: string;
  cancellation_reason?: string;
  meeting_link?: string;
  created_at: string;
};

export default function AppointmentsPage() {
  const [doctors, setDoctors] = useState<Doctor[]>([]);
  const [loadingDoctors, setLoadingDoctors] = useState<boolean>(false);
  const [doctorsError, setDoctorsError] = useState<string>('');

  const [selectedDoctorId, setSelectedDoctorId] = useState<string>('');
  const [doctorAvailabilities, setDoctorAvailabilities] = useState<Availability[]>([]);
  const [loadingAvailabilities, setLoadingAvailabilities] = useState<boolean>(false);
  const [availabilityError, setAvailabilityError] = useState<string>('');

  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [loadingAppointments, setLoadingAppointments] = useState<boolean>(true);
  const [appointmentsError, setAppointmentsError] = useState<string>('');
  const [page, setPage] = useState<number>(1);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [hasNextPage, setHasNextPage] = useState<boolean>(false);
  const [hasPrevPage, setHasPrevPage] = useState<boolean>(false);
  const appointmentsReqIdRef = useRef<number>(0);

  // Booking Form State
  const [bookForm, setBookForm] = useState({
    scheduled_start: '',
    scheduled_end: '',
    reason: '',
    symptoms: ''
  });
  const [isSubmittingBooking, setIsSubmittingBooking] = useState<boolean>(false);
  const [bookingError, setBookingError] = useState<string>('');
  const [bookingSuccess, setBookingSuccess] = useState<string>('');

  // Reschedule State
  const [reschedulingAppointment, setReschedulingAppointment] = useState<Appointment | null>(null);
  const [rescheduleForm, setRescheduleForm] = useState({ scheduled_start: '', scheduled_end: '' });
  const [isSubmittingReschedule, setIsSubmittingReschedule] = useState<boolean>(false);
  const [rescheduleError, setRescheduleError] = useState<string>('');

  // Cancel State
  const [cancellingAppointment, setCancellingAppointment] = useState<Appointment | null>(null);
  const [cancellationReason, setCancellationReason] = useState<string>('');
  const [isSubmittingCancel, setIsSubmittingCancel] = useState<boolean>(false);
  const [cancelError, setCancelError] = useState<string>('');

  // Load doctors and initial appointments
  useEffect(() => {
    loadDoctors();
    loadAppointments(1);
  }, []);

  // When selected doctor changes, fetch their active availability with race-condition guard
  useEffect(() => {
    if (!selectedDoctorId) {
      setDoctorAvailabilities([]);
      setAvailabilityError('');
      setLoadingAvailabilities(false);
      return;
    }

    let isCurrent = true;
    setLoadingAvailabilities(true);
    setAvailabilityError('');

    async function fetchAvailability() {
      try {
        let allAvail: Availability[] = [];
        let nextUrl: string | null = `/api/appointments/availability/?doctor=${selectedDoctorId}&is_active=true`;

        while (nextUrl && isCurrent) {
          const data: any = await apiFetch<any>(nextUrl);
          if (!isCurrent) return;

          if (Array.isArray(data)) {
            allAvail = data;
            break;
          }
          allAvail = [...allAvail, ...(data.results || [])];
          nextUrl = data.next ? data.next.replace(/^https?:\/\/[^/]+/, '') : null;
        }

        if (isCurrent) {
          setDoctorAvailabilities(allAvail);
        }
      } catch (err: any) {
        if (isCurrent) {
          setDoctorAvailabilities([]);
          setAvailabilityError(err.message || 'Failed to load doctor availability windows.');
        }
      } finally {
        if (isCurrent) {
          setLoadingAvailabilities(false);
        }
      }
    }

    fetchAvailability();

    return () => {
      isCurrent = false;
    };
  }, [selectedDoctorId]);

  async function loadDoctors() {
    setLoadingDoctors(true);
    setDoctorsError('');
    try {
      let allDocs: Doctor[] = [];
      let nextUrl: string | null = '/api/auth/doctors/';

      while (nextUrl) {
        const data: any = await apiFetch<any>(nextUrl);
        if (Array.isArray(data)) {
          allDocs = data;
          break;
        }
        allDocs = [...allDocs, ...(data.results || [])];
        nextUrl = data.next ? data.next.replace(/^https?:\/\/[^/]+/, '') : null;
      }
      setDoctors(allDocs);
    } catch (err: any) {
      setDoctorsError(err.message || 'Failed to load doctors list.');
    } finally {
      setLoadingDoctors(false);
    }
  }

  async function loadAppointments(pageNumber: number = 1) {
    const reqId = ++appointmentsReqIdRef.current;
    setLoadingAppointments(true);
    setAppointmentsError('');
    try {
      const data = await apiFetch<any>(`/api/appointments/?page=${pageNumber}`);
      if (reqId !== appointmentsReqIdRef.current) return;

      if (Array.isArray(data)) {
        setAppointments(data);
        setTotalCount(data.length);
        setHasNextPage(false);
        setHasPrevPage(false);
        setPage(1);
      } else {
        const results = data.results || [];
        const count = data.count !== undefined ? data.count : results.length;

        // Handle last item disappearing from a filtered/subsequent page
        if (results.length === 0 && pageNumber > 1) {
          return loadAppointments(pageNumber - 1);
        }

        setAppointments(results);
        setTotalCount(count);
        setHasNextPage(Boolean(data.next));
        setHasPrevPage(Boolean(data.previous));
        setPage(pageNumber);
      }
    } catch (err: any) {
      if (reqId !== appointmentsReqIdRef.current) return;
      if (isInvalidPageError(err) && pageNumber > 1) {
        return loadAppointments(pageNumber - 1);
      }
      setAppointments([]);
      setAppointmentsError(err.message || 'Failed to load appointments.');
    } finally {
      if (reqId === appointmentsReqIdRef.current) {
        setLoadingAppointments(false);
      }
    }
  }

  async function handleBookSubmit(event: FormEvent) {
    event.preventDefault();
    setBookingError('');
    setBookingSuccess('');

    if (!selectedDoctorId) {
      setBookingError('Please select a doctor.');
      return;
    }

    const startIso = toIsoTimestamp(bookForm.scheduled_start);
    const endIso = toIsoTimestamp(bookForm.scheduled_end);

    if (!startIso || !endIso) {
      setBookingError('Please provide valid start and end dates.');
      return;
    }

    const symptomsList = bookForm.symptoms
      ? bookForm.symptoms.split(',').map((s) => s.trim()).filter(Boolean)
      : [];

    setIsSubmittingBooking(true);
    try {
      await apiFetch<Appointment>('/api/appointments/', {
        method: 'POST',
        body: JSON.stringify({
          doctor: selectedDoctorId,
          scheduled_start: startIso,
          scheduled_end: endIso,
          reason: bookForm.reason,
          symptoms: symptomsList
        })
      });

      setBookingSuccess('Appointment booked successfully! Status is pending doctor confirmation.');
      setBookForm({ scheduled_start: '', scheduled_end: '', reason: '', symptoms: '' });
      await loadAppointments(1);
    } catch (err: any) {
      setBookingError(err.message || 'Booking failed.');
    } finally {
      setIsSubmittingBooking(false);
    }
  }

  async function handleRescheduleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!reschedulingAppointment) return;
    setRescheduleError('');

    const startIso = toIsoTimestamp(rescheduleForm.scheduled_start);
    const endIso = toIsoTimestamp(rescheduleForm.scheduled_end);

    if (!startIso || !endIso) {
      setRescheduleError('Please specify valid new start and end times.');
      return;
    }

    setIsSubmittingReschedule(true);
    try {
      await apiFetch<Appointment>(`/api/appointments/${reschedulingAppointment.id}/`, {
        method: 'PATCH',
        body: JSON.stringify({
          scheduled_start: startIso,
          scheduled_end: endIso
        })
      });

      setReschedulingAppointment(null);
      await loadAppointments(page);
    } catch (err: any) {
      setRescheduleError(err.message || 'Rescheduling failed.');
    } finally {
      setIsSubmittingReschedule(false);
    }
  }

  async function handleCancelSubmit(event: FormEvent) {
    event.preventDefault();
    if (!cancellingAppointment) return;
    setCancelError('');

    setIsSubmittingCancel(true);
    try {
      await apiFetch<Appointment>(`/api/appointments/${cancellingAppointment.id}/cancel/`, {
        method: 'POST',
        body: JSON.stringify({
          cancellation_reason: cancellationReason
        })
      });

      setCancellingAppointment(null);
      setCancellationReason('');
      await loadAppointments(page);
    } catch (err: any) {
      setCancelError(err.message || 'Cancellation failed.');
    } finally {
      setIsSubmittingCancel(false);
    }
  }

  function getStatusBadge(status: string) {
    switch (status) {
      case 'confirmed':
        return <span className="rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-bold text-emerald-800">Confirmed</span>;
      case 'completed':
        return <span className="rounded-full bg-sky-100 px-2.5 py-0.5 text-xs font-bold text-sky-800">Completed</span>;
      case 'cancelled':
        return <span className="rounded-full bg-rose-100 px-2.5 py-0.5 text-xs font-bold text-rose-800">Cancelled</span>;
      case 'no_show':
        return <span className="rounded-full bg-slate-200 px-2.5 py-0.5 text-xs font-bold text-slate-800">No Show</span>;
      case 'pending':
      default:
        return <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-bold text-amber-800">Pending</span>;
    }
  }

  return (
    <main className="app-shell pb-16">
      <AppNav />
      <div className="mx-auto max-w-6xl px-5 pt-8">
        <h1 className="text-3xl font-black text-slate-900">Patient Appointments</h1>
        <p className="mt-1 text-slate-600">Schedule a new consultation and manage your appointments.</p>
      </div>

      <section className="mx-auto mt-6 grid max-w-6xl gap-6 px-5 lg:grid-cols-[1fr_1.3fr]">
        {/* Booking & Availability Panel */}
        <div className="flex flex-col gap-6">
          <form onSubmit={handleBookSubmit} className="panel p-6">
            <h2 className="flex items-center gap-2 text-xl font-black text-slate-900">
              <CalendarPlus className="h-5 w-5 text-teal-600" aria-hidden />
              Book Appointment
            </h2>

            {bookingSuccess && (
              <div className="mt-4 flex items-center gap-2 rounded-md bg-emerald-50 p-3 text-sm font-semibold text-emerald-800 border border-emerald-200">
                <CheckCircle2 className="h-4 w-4 shrink-0" />
                <span>{bookingSuccess}</span>
              </div>
            )}

            {bookingError && (
              <div className="mt-4 flex items-center gap-2 rounded-md bg-rose-50 p-3 text-sm font-semibold text-rose-800 border border-rose-200">
                <AlertCircle className="h-4 w-4 shrink-0" />
                <span>{bookingError}</span>
              </div>
            )}

            <div className="mt-5 grid gap-4">
              <div>
                <label className="block text-xs font-bold uppercase tracking-wider text-slate-700">Select Doctor</label>
                <select
                  className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-teal-500 focus:outline-none"
                  value={selectedDoctorId}
                  onChange={(e) => setSelectedDoctorId(e.target.value)}
                  required
                  disabled={loadingDoctors}
                >
                  <option value="">-- Choose a doctor --</option>
                  {doctors.map((doc) => (
                    <option key={doc.id} value={doc.id}>
                      {doc.profile?.full_name || doc.email} {doc.doctor_profile?.specialty ? `(${doc.doctor_profile.specialty})` : ''}
                    </option>
                  ))}
                </select>
                {doctorsError && (
                  <div className="mt-1.5 flex items-center justify-between text-xs text-rose-700">
                    <span>{doctorsError}</span>
                    <button type="button" onClick={loadDoctors} className="font-semibold underline hover:text-rose-900">
                      Retry
                    </button>
                  </div>
                )}
              </div>

              {/* Doctor Availability Section */}
              {selectedDoctorId && (
                <div className="rounded-lg border border-teal-100 bg-teal-50/50 p-4">
                  <div className="flex items-center justify-between">
                    <span className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-teal-900">
                      <Clock className="h-3.5 w-3.5" />
                      Doctor Availability
                    </span>
                    <span className="rounded bg-teal-100 px-2 py-0.5 text-[11px] font-semibold text-teal-800">
                      Timezone: UTC
                    </span>
                  </div>

                  {loadingAvailabilities ? (
                    <div className="mt-3 flex items-center gap-2 text-xs text-slate-500">
                      <RefreshCw className="h-3.5 w-3.5 animate-spin text-teal-600" />
                      Loading availability windows...
                    </div>
                  ) : availabilityError ? (
                    <div className="mt-2.5 rounded bg-rose-50 p-2.5 text-xs text-rose-800 border border-rose-200">
                      <div className="flex items-center justify-between">
                        <span className="flex items-center gap-1.5">
                          <AlertCircle className="h-3.5 w-3.5 shrink-0" />
                          {availabilityError}
                        </span>
                        <button
                          type="button"
                          onClick={() => {
                            const curId = selectedDoctorId;
                            setSelectedDoctorId('');
                            setTimeout(() => setSelectedDoctorId(curId), 10);
                          }}
                          className="font-bold underline ml-2 hover:text-rose-950"
                        >
                          Retry
                        </button>
                      </div>
                    </div>
                  ) : doctorAvailabilities.length > 0 ? (
                    <div className="mt-2.5 grid gap-1.5 text-xs">
                      {doctorAvailabilities.map((avail) => (
                        <div key={avail.id} className="flex items-center justify-between rounded bg-white px-2.5 py-1.5 shadow-sm border border-teal-50">
                          <span className="font-semibold text-slate-800">{WEEKDAYS[avail.weekday]}</span>
                          <span className="font-mono text-slate-600">{avail.start_time.slice(0, 5)} - {avail.end_time.slice(0, 5)} UTC</span>
                        </div>
                      ))}
                      <p className="mt-1 text-[11px] text-slate-500">
                        * Bookings are matched to UTC doctor availability windows. Datetimes are converted automatically.
                      </p>
                    </div>
                  ) : (
                    <div className="mt-2.5 flex items-center gap-1.5 text-xs text-amber-700">
                      <Info className="h-4 w-4 shrink-0" />
                      <span>This doctor currently has no active availability windows published.</span>
                    </div>
                  )}
                </div>
              )}

              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label className="block text-xs font-bold uppercase tracking-wider text-slate-700">Scheduled Start</label>
                  <input
                    type="datetime-local"
                    className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-teal-500 focus:outline-none"
                    value={bookForm.scheduled_start}
                    onChange={(e) => setBookForm({ ...bookForm, scheduled_start: e.target.value })}
                    required
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold uppercase tracking-wider text-slate-700">Scheduled End</label>
                  <input
                    type="datetime-local"
                    className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-teal-500 focus:outline-none"
                    value={bookForm.scheduled_end}
                    onChange={(e) => setBookForm({ ...bookForm, scheduled_end: e.target.value })}
                    required
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold uppercase tracking-wider text-slate-700">Reason for Visit</label>
                <textarea
                  className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-teal-500 focus:outline-none"
                  rows={2}
                  placeholder="e.g. Annual wellness checkup, persistent cough, etc."
                  value={bookForm.reason}
                  onChange={(e) => setBookForm({ ...bookForm, reason: e.target.value })}
                  required
                />
              </div>

              <div>
                <label className="block text-xs font-bold uppercase tracking-wider text-slate-700">Symptoms (comma-separated, optional)</label>
                <input
                  type="text"
                  className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-teal-500 focus:outline-none"
                  placeholder="fever, headache, fatigue"
                  value={bookForm.symptoms}
                  onChange={(e) => setBookForm({ ...bookForm, symptoms: e.target.value })}
                />
              </div>

              <button
                type="submit"
                disabled={isSubmittingBooking}
                className="btn btn-primary mt-2 justify-center py-2.5 text-sm"
              >
                {isSubmittingBooking ? (
                  <>
                    <RefreshCw className="h-4 w-4 animate-spin" />
                    Booking appointment...
                  </>
                ) : (
                  <>
                    <CalendarPlus className="h-4 w-4" />
                    Book Consultation
                  </>
                )}
              </button>
            </div>
          </form>
        </div>

        {/* Appointments List Panel */}
        <div className="panel p-6">
          <div className="flex items-center justify-between border-b border-slate-100 pb-4">
            <div>
              <h2 className="text-xl font-black text-slate-900">Your Appointments</h2>
              <p className="text-xs text-slate-500">{totalCount} total appointment{totalCount === 1 ? '' : 's'}</p>
            </div>
            <button
              onClick={() => loadAppointments(page)}
              className="btn btn-secondary px-2.5 py-1.5 text-xs text-slate-600"
              title="Refresh appointments"
              disabled={loadingAppointments}
            >
              <RefreshCw className={`h-3.5 w-3.5 ${loadingAppointments ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          </div>

          {loadingAppointments ? (
            <div className="py-12 text-center text-sm text-slate-500">
              <RefreshCw className="mx-auto h-6 w-6 animate-spin text-teal-600 mb-2" />
              Loading appointments...
            </div>
          ) : appointmentsError ? (
            <div className="my-6 rounded-lg border border-rose-200 bg-rose-50 p-4 text-center">
              <AlertCircle className="mx-auto h-8 w-8 text-rose-500" />
              <p className="mt-2 text-sm font-semibold text-rose-800">{appointmentsError}</p>
              <button
                onClick={() => loadAppointments(page)}
                className="btn btn-secondary mt-3 inline-flex text-xs text-rose-800 border-rose-300 hover:bg-rose-100"
              >
                <RefreshCw className="h-3.5 w-3.5" />
                Retry
              </button>
            </div>
          ) : appointments.length === 0 ? (
            <div className="py-12 text-center">
              <Calendar className="mx-auto h-10 w-10 text-slate-300" />
              <p className="mt-3 text-sm font-semibold text-slate-700">No appointments scheduled yet.</p>
              <p className="text-xs text-slate-500 mt-1">Book a consultation using the form on the left.</p>
            </div>
          ) : (
            <div className="mt-4 grid gap-3.5">
              {appointments.map((appt) => (
                <article key={appt.id} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm transition hover:border-slate-300">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <span className="font-bold text-slate-900">{appt.reason}</span>
                      <div className="mt-0.5 flex items-center gap-1.5 text-xs text-slate-600">
                        <Stethoscope className="h-3.5 w-3.5 text-teal-600" />
                        <span>Doctor: {appt.doctor_detail?.profile?.full_name || appt.doctor_detail?.email || appt.doctor}</span>
                      </div>
                    </div>
                    {getStatusBadge(appt.status)}
                  </div>

                  <div className="mt-3 flex flex-wrap items-center gap-4 text-xs text-slate-500">
                    <span className="flex items-center gap-1">
                      <Clock className="h-3.5 w-3.5 text-slate-400" />
                      {new Date(appt.scheduled_start).toLocaleString()} - {new Date(appt.scheduled_end).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                    {appt.meeting_link && appt.status === 'confirmed' && (
                      <a
                        href={appt.meeting_link}
                        target="_blank"
                        rel="noreferrer"
                        className="font-bold text-teal-700 hover:underline"
                      >
                        Join Video Room
                      </a>
                    )}
                  </div>

                  {appt.cancellation_reason && (
                    <div className="mt-2 text-xs text-rose-700 bg-rose-50 p-2 rounded border border-rose-100">
                      <strong>Cancellation Reason:</strong> {appt.cancellation_reason}
                    </div>
                  )}

                  {/* Actions according to status */}
                  <div className="mt-3 flex items-center gap-2 border-t border-slate-100 pt-3">
                    {appt.status === 'pending' && (
                      <button
                        onClick={() => {
                          setReschedulingAppointment(appt);
                          setRescheduleError('');
                        }}
                        className="rounded border border-slate-300 px-3 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                      >
                        Reschedule
                      </button>
                    )}
                    {(appt.status === 'pending' || appt.status === 'confirmed') && (
                      <button
                        onClick={() => {
                          setCancellingAppointment(appt);
                          setCancelError('');
                        }}
                        className="rounded border border-rose-200 px-3 py-1 text-xs font-semibold text-rose-700 hover:bg-rose-50"
                      >
                        Cancel
                      </button>
                    )}
                  </div>
                </article>
              ))}

              {/* Pagination controls using API metadata */}
              {(hasPrevPage || hasNextPage || totalCount > 10) && (
                <div className="mt-4 flex items-center justify-between border-t border-slate-100 pt-4 text-xs font-semibold text-slate-600">
                  <button
                    disabled={!hasPrevPage || page <= 1}
                    onClick={() => loadAppointments(page - 1)}
                    className="flex items-center gap-1 rounded border border-slate-200 px-3 py-1.5 disabled:opacity-40"
                  >
                    <ChevronLeft className="h-3.5 w-3.5" /> Previous
                  </button>
                  <span>Page {page}</span>
                  <button
                    disabled={!hasNextPage}
                    onClick={() => loadAppointments(page + 1)}
                    className="flex items-center gap-1 rounded border border-slate-200 px-3 py-1.5 disabled:opacity-40"
                  >
                    Next <ChevronRight className="h-3.5 w-3.5" />
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </section>

      {/* Reschedule Modal */}
      {reschedulingAppointment && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
          <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <h3 className="font-bold text-slate-900">Reschedule Appointment</h3>
              <button onClick={() => setReschedulingAppointment(null)} className="text-slate-400 hover:text-slate-600">
                <X className="h-4 w-4" />
              </button>
            </div>

            {rescheduleError && (
              <div className="mt-3 flex items-center gap-2 rounded bg-rose-50 p-2.5 text-xs text-rose-800 border border-rose-200">
                <AlertCircle className="h-4 w-4 shrink-0" />
                <span>{rescheduleError}</span>
              </div>
            )}

            <form onSubmit={handleRescheduleSubmit} className="mt-4 grid gap-3 text-xs">
              <div>
                <label className="block font-bold uppercase text-slate-700">New Scheduled Start</label>
                <input
                  type="datetime-local"
                  className="mt-1 w-full rounded border border-slate-300 p-2 text-sm"
                  value={rescheduleForm.scheduled_start}
                  onChange={(e) => setRescheduleForm({ ...rescheduleForm, scheduled_start: e.target.value })}
                  required
                />
              </div>
              <div>
                <label className="block font-bold uppercase text-slate-700">New Scheduled End</label>
                <input
                  type="datetime-local"
                  className="mt-1 w-full rounded border border-slate-300 p-2 text-sm"
                  value={rescheduleForm.scheduled_end}
                  onChange={(e) => setRescheduleForm({ ...rescheduleForm, scheduled_end: e.target.value })}
                  required
                />
              </div>

              <div className="mt-3 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setReschedulingAppointment(null)}
                  className="rounded border border-slate-300 px-3 py-1.5 font-semibold text-slate-700 hover:bg-slate-50"
                >
                  Close
                </button>
                <button
                  type="submit"
                  disabled={isSubmittingReschedule}
                  className="rounded bg-teal-600 px-4 py-1.5 font-semibold text-white shadow hover:bg-teal-700 disabled:opacity-50"
                >
                  {isSubmittingReschedule ? 'Saving...' : 'Confirm Reschedule'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Cancel Modal */}
      {cancellingAppointment && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
          <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <h3 className="font-bold text-slate-900">Cancel Appointment</h3>
              <button onClick={() => setCancellingAppointment(null)} className="text-slate-400 hover:text-slate-600">
                <X className="h-4 w-4" />
              </button>
            </div>

            {cancelError && (
              <div className="mt-3 flex items-center gap-2 rounded bg-rose-50 p-2.5 text-xs text-rose-800 border border-rose-200">
                <AlertCircle className="h-4 w-4 shrink-0" />
                <span>{cancelError}</span>
              </div>
            )}

            <form onSubmit={handleCancelSubmit} className="mt-4 grid gap-3 text-xs">
              <p className="text-slate-600 text-sm">
                Are you sure you want to cancel this appointment for <strong>{cancellingAppointment.reason}</strong>?
              </p>
              <div>
                <label className="block font-bold uppercase text-slate-700">Cancellation Reason (optional)</label>
                <input
                  type="text"
                  className="mt-1 w-full rounded border border-slate-300 p-2 text-sm"
                  placeholder="e.g. Schedule conflict, feeling better"
                  value={cancellationReason}
                  onChange={(e) => setCancellationReason(e.target.value)}
                />
              </div>

              <div className="mt-3 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setCancellingAppointment(null)}
                  className="rounded border border-slate-300 px-3 py-1.5 font-semibold text-slate-700 hover:bg-slate-50"
                >
                  Go Back
                </button>
                <button
                  type="submit"
                  disabled={isSubmittingCancel}
                  className="rounded bg-rose-600 px-4 py-1.5 font-semibold text-white shadow hover:bg-rose-700 disabled:opacity-50"
                >
                  {isSubmittingCancel ? 'Cancelling...' : 'Confirm Cancellation'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </main>
  );
}
