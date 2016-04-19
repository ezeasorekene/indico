# This file is part of Indico.
# Copyright (C) 2002 - 2016 European Organization for Nuclear Research (CERN).
#
# Indico is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of the
# License, or (at your option) any later version.
#
# Indico is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Indico; if not, see <http://www.gnu.org/licenses/>.

from __future__ import unicode_literals

from io import BytesIO
from lxml import html
from lxml.etree import ParserError

import icalendar as ical
from pyatom import AtomFeed
from sqlalchemy.orm import joinedload, load_only, subqueryload

from indico.modules.events import Event
from indico.util.date_time import now_utc
from indico.util.string import to_unicode
from indico.web.flask.util import url_for


def serialize_category_ical(category, user, event_filter):
    """Export the events in a category to iCal

    :param category: The category to export
    :param user: The user who needs to be able to access the events
    :param event_filter: A SQLalchemy criterion to restrict which
                         events will be returned.  Usually something
                         involving the start/end date of the event.
    """
    own_room_strategy = joinedload('own_room')
    own_room_strategy.load_only('building', 'floor', 'number', 'name')
    own_room_strategy.lazyload('owner')
    own_venue_strategy = joinedload('own_venue').load_only('name')
    query = (Event.query
             .filter(Event.category_chain.contains([int(category.getId())]),
                     ~Event.is_deleted,
                     event_filter)
             .options(load_only('id', 'start_dt', 'end_dt', 'title', 'description', 'own_venue_name',
                                'own_room_name', 'protection_mode'),
                      subqueryload('acl_entries'),
                      joinedload('person_links'),
                      own_room_strategy,
                      own_venue_strategy)
             .order_by(Event.start_dt))
    events = [e for e in query if e.can_access(user)]
    cal = ical.Calendar()
    cal.add('version', '2.0')
    cal.add('prodid', '-//CERN//INDICO//EN')

    now = now_utc(False)
    for event in events:
        url = url_for('event.conferenceDisplay', confId=event.id, _external=True)
        location = ('{} ({})'.format(event.room_name, event.venue_name)
                    if event.venue_name and event.room_name
                    else (event.venue_name or event.room_name))
        cal_event = ical.Event()
        cal_event.add('uid', u'indico-event-{}@cern.ch'.format(event.id))
        cal_event.add('dtstamp', now)
        cal_event.add('dtstart', event.start_dt)
        cal_event.add('dtend', event.end_dt)
        cal_event.add('url', url)
        cal_event.add('summary', event.title)
        cal_event.add('location', location)
        description = []
        if event.person_links:
            speakers = [u'{} ({})'.format(x.full_name, x.affiliation) if x.affiliation else x.full_name
                        for x in event.person_links]
            description.append(u'Speakers: {}'.format(u', '.join(speakers)))

        if event.description:
            desc_text = unicode(event.description) or u'<p/>'  # get rid of RichMarkup
            try:
                description.append(unicode(html.fromstring(desc_text).text_content()))
            except ParserError:
                # this happens e.g. if desc_text contains only a html comment
                pass
        description.append(url)
        cal_event.add('description', u'\n'.join(description))
        cal.add_component(cal_event)
    return BytesIO(cal.to_ical())


def serialize_category_atom(category, url, user, event_filter):
    """Export the events in a category to Atom

    :param category: The category to export
    :param url: The URL of the feed
    :param user: The user who needs to be able to access the events
    :param event_filter: A SQLalchemy criterion to restrict which
                         events will be returned.  Usually something
                         involving the start/end date of the event.
    """
    query = (Event.query
             .filter(Event.category_chain.contains([int(category.getId())]),
                     ~Event.is_deleted,
                     event_filter)
             .options(load_only('id', 'start_dt', 'title', 'description', 'protection_mode'),
                      subqueryload('acl_entries'))
             .order_by(Event.start_dt))
    events = [e for e in query if e.can_access(user)]

    feed = AtomFeed(feed_url=url, title='Indico Feed [{}]'.format(to_unicode(category.getTitle())))
    for event in events:
        feed.add(title=event.title,
                 summary=unicode(event.description),  # get rid of RichMarkup
                 url=url_for('event.conferenceDisplay', confId=event.id, _external=True),
                 updated=event.start_dt)
    return BytesIO(feed.to_string().encode('utf-8'))